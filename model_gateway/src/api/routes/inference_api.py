"""
OpenAI-compatible inference routing and proxy handlers (FR-001, FR-005, FR-007, FR-009, FR-053, FR-070, FR-071).
Provides GET /v1/models catalog listing and reverse-proxying for RAG/Agent requests with Dual-LLM architecture:
- qwen3.5-9b (port 8089, synthesis_llm / default)
- qwen3.5-4b (port 8088, router_llm / fast)
- bge-m3 (port 8090, embedding)
- bge-reranker-v2-m3 (port 8091, reranker)
"""

import os
import sys
import time
import json
import math
import logging
import asyncio
from typing import Any, AsyncGenerator, Optional
import httpx
import anyio
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from src.core.llama_manager import llama_manager
from src.core.auxiliary_manager import auxiliary_manager
from src.core.config_manager import ConfigManager
from src.core.model_downloader import ModelDownloader
from src.core.process_manager import ProcessStatusEnum
from src.core.client_logger import get_client_logger
from src.core.redis_manager import redis_manager
from src.core.queue_manager import (
    gpu_queue,
    QueueFullError,
    validate_pre_queue_prompt_limits,
    try_acquire_slot_nonblocking,
    format_queue_status_event,
)
from src.core.queue_models import QueueStateEnum, compute_prompt_hash

logger = logging.getLogger("InferenceAPI")

router = APIRouter()

VALID_CHAT_MODELS = {
    "qwen3.5-9b",
    "qwen3.5-9b-instruct",
    "qwen3.5-4b",
    "qwen3.5-4b-instruct",
    "default",
    "fast",
    "synthesis",
}

QWEN_CHATML_STOPS = ["<|im_end|>", "<|im_start|>", "<|endoftext|>"]


def normalize_rerank_response(res: dict) -> dict:
    """T015 / T016: Dual mapping of rerank results (res['data'] = res['results']) for backward compatibility."""
    if isinstance(res, dict):
        if "results" in res and "data" not in res:
            res["data"] = res["results"]
        elif "data" in res and "results" not in res:
            res["results"] = res["data"]
    return res


# ═══════════════════════════════════════════════════════════════════════════════
# Spec 031: GPU Queue Management Endpoints (FR-008, FR-009)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/v1/queue/cancel")
async def cancel_queue_request(request: Request) -> dict:
    """Spec 031 FR-008: 대기 중인 요청을 명시적으로 취소하고 큐에서 즉시 Purge (Unified Contract Schema)."""
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse cancel queue body: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    ticket_id = body.get("ticket_id", "")
    if not ticket_id:
        raise HTTPException(status_code=400, detail="ticket_id is required.")

    res = await gpu_queue.cancel(ticket_id)
    if not res.get("success"):
        raise HTTPException(
            status_code=404,
            detail=f"Ticket '{ticket_id}' not found or already completed."
        )
    return res


@router.get("/v1/queue/stats")
async def get_queue_stats() -> dict:
    """Spec 031: GPU 큐 전체 통계 조회 (관리/모니터링용)."""
    return gpu_queue.get_stats()


def _get_llama_server_config() -> tuple[int, str]:
    """FR-009: 백엔드 LLM 엔진 포트를 config/server_config.json에서 동적 로드 (로컬 백엔드 통신은 127.0.0.1 사용)."""
    try:
        cm = ConfigManager()
        server_cfg = cm.get_server_config()
        port = server_cfg.get("backend_port", 8089)
        return port, "127.0.0.1"
    except Exception as e:
        logger.error(f"Error loading server config: {e}")
        return 8089, "127.0.0.1"


_port, _host = _get_llama_server_config()
LLAMA_SERVER_PORT = _port
LLAMA_SERVER_URL = f"http://{_host}:{LLAMA_SERVER_PORT}"


def _build_default_client() -> httpx.AsyncClient:
    """FR-005 & FR-009 & FR-052: 커넥션 풀 및 백엔드 타임아웃(5s/120s) 설정으로 싱글톤 구성."""
    try:
        cm = ConfigManager()
        server_cfg = cm.get_server_config()
        pool_cfg = server_cfg.get("connection_pool", {})
        max_keepalive = pool_cfg.get("max_keepalive_connections", 20)
        max_conn = pool_cfg.get("max_connections", 100)
    except Exception as e:
        logger.error(f"Error reading connection pool config: {e}")
        max_keepalive = 20
        max_conn = 100

    return httpx.AsyncClient(
        base_url=LLAMA_SERVER_URL,
        limits=httpx.Limits(max_keepalive_connections=max_keepalive, max_connections=max_conn),
        timeout=httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)
    )


_default_client = _build_default_client()


def parse_response_format(body: dict[str, Any]) -> dict[str, Any]:
    """FR-002: OpenAI response_format 파라미터를 파싱하여 llama-server 문법 규격으로 변환."""
    response_format = body.get("response_format")
    if not response_format or not isinstance(response_format, dict):
        return body

    fmt_type = response_format.get("type")
    if fmt_type == "json_object":
        body["grammar"] = "json"
    elif fmt_type == "json_schema" and "json_schema" in response_format:
        schema = response_format["json_schema"]
        if "schema" in schema:
            body["json_schema"] = schema["schema"]
    return body


async def check_llama_status() -> bool:
    """Check if the backend LLM engine is ready to accept requests (Zero-Mock verified)."""
    return llama_manager.is_ready()


def _get_http_client(request: Request) -> httpx.AsyncClient:
    """Helper to retrieve singleton AsyncClient from app.state or fallback."""
    if hasattr(request.app.state, "http_client") and request.app.state.http_client:
        return request.app.state.http_client
    return _default_client


@router.get("/v1/models")
async def list_models(request: Request) -> dict[str, Any]:
    """FR-001 & FR-007 & Spec 033: OpenAI API 표준 GET /v1/models 동적 모델 카탈로그 엔드포인트."""
    cm = ConfigManager()
    catalog = cm.get_model_catalog()
    downloader = ModelDownloader(config_manager=cm)

    created_ts = int(time.time())
    models_data = []

    for model_id, entry in catalog.items():
        is_available = downloader.is_model_available(model_id)
        pm = llama_manager.get_pm_for_model(model_id)
        is_active = pm.is_ready() if pm else False
        is_resident = True
        n_ctx = entry.get("context_window", 32768 if "9b" in model_id else 8192)

        models_data.append({
            "id": model_id,
            "object": "model",
            "created": created_ts,
            "owned_by": "model-gateway",
            "permission": [],
            "is_available": is_available,
            "is_active": is_active,
            "is_resident": is_resident,
            "current_n_ctx": n_ctx,
        })

    # Always ensure resident helper models are visible
    for aux_id, ctx in (("bge-m3", 2048), ("bge-reranker-v2-m3", 2048)):
        if not any(m["id"] == aux_id for m in models_data):
            models_data.append({
                "id": aux_id,
                "object": "model",
                "created": created_ts,
                "owned_by": "model-gateway",
                "permission": [],
                "is_available": True,
                "is_active": True,
                "is_resident": True,
                "current_n_ctx": ctx,
            })

    return {"object": "list", "data": models_data}


@router.get("/v1/profile")
async def get_profile(request: Request) -> dict[str, Any]:
    """Spec 033 & Spec 034 & Spec 036: 3-Axis Decoupled Hardware & Active Resident Model Profile Endpoint."""
    cm = ConfigManager()
    from src.core.gpu_detector import detect_hardware_capabilities
    hardware_profile = detect_hardware_capabilities()

    return {
        "status": "healthy",
        "active_model": "qwen3.5-9b",
        "current_n_ctx": 32768,
        "dynamic_n_ctx_max": hardware_profile.dynamic_n_ctx,
        "hardware_tier": hardware_profile.hardware_tier.value,
        "serving_strategy": {
            "resident_model": "qwen3.5-9b",
            "resident_standard_n_ctx": 32768,
            "resident_ultra_n_ctx": 32768,
            "batch_model": "qwen3.5-4b",
            "batch_n_ctx": 8192,
            "min_target_tps": hardware_profile.min_target_tps,
        },
        "hardware": hardware_profile.model_dump(),
        "vram_total_mb": hardware_profile.total_vram_mb,
        "vram_used_mb": max(0, hardware_profile.total_vram_mb - hardware_profile.free_vram_mb),
        "single_model_mode": False,
    }


@router.get("/v1/hardware/capacity")
async def get_hardware_capacity(request: Request) -> dict[str, Any]:
    """Spec 036: VRAM Capacity Inspection Endpoint for tiered serving strategy."""
    from src.core.gpu_detector import detect_hardware_capabilities
    hw = detect_hardware_capabilities()

    return {
        "hardware_tier": hw.hardware_tier.value,
        "device_name": hw.device_name,
        "compute_capability": hw.compute_capability,
        "total_vram_mb": hw.total_vram_mb,
        "free_vram_mb": hw.free_vram_mb,
        "vram_used_mb": max(0, hw.total_vram_mb - hw.free_vram_mb),
        "gpu_architecture": hw.gpu_features.architecture_name,
        "supports_flash_attn": hw.use_flash_attn,
        "kv_cache_type": hw.gpu_features.recommended_kv_type,
        "serving_capacity": {
            "resident_model": "qwen3.5-9b",
            "resident_standard_n_ctx": 32768,
            "resident_ultra_n_ctx": 32768,
            "batch_model": "qwen3.5-4b",
            "batch_n_ctx": 8192,
            "min_target_tps": hw.min_target_tps,
            "dynamic_n_ctx_max": hw.dynamic_n_ctx,
        },
    }


def _get_backend_target_port(path: str, model_id: Optional[str] = None) -> int:
    """T017 / FR-007: Dynamically route 4B/fast -> 8088 and 9B/default -> 8089, Aux -> 8090/8091."""
    clean_path = path.strip("/").split("/")[-1]
    if clean_path in ("embeddings", "embedding"):
        return 8090
    elif clean_path in ("rerank", "reranking"):
        return 8091

    if model_id:
        mid = model_id.lower()
        if "4b" in mid or "fast" in mid:
            return 8088
        if "9b" in mid or "default" in mid or "synthesis" in mid:
            return 8089

    return 8089


@router.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
@router.api_route("/embedding", methods=["POST", "OPTIONS"])
@router.api_route("/v1/embedding", methods=["POST", "OPTIONS"])
@router.api_route("/rerank", methods=["POST", "OPTIONS"])
@router.api_route("/v1/rerank", methods=["POST", "OPTIONS"])
async def reverse_proxy(request: Request, path: str = "") -> StreamingResponse:
    """FR-009, FR-002, FR-007, FR-053: RAG, Agent, Embedding, Reranker 요청을 백엔드 싱글톤 인스턴스로 역방향 프록시 라우팅."""
    # T038 / FR-060 / FR-074: Graceful Lifespan Active Drain Mode rejection
    if getattr(request.app.state, "drain_mode", False) is True:
        raise HTTPException(
            status_code=503,
            detail="Service is shutting down (drain mode active).",
            headers={"Retry-After": "15"}
        )

    if not path:
        path = request.url.path.strip("/")

    clean_path = path.strip("/").split("/")[-1]

    # Spec 019: Rate limiter check (FR-005, US4)
    client_ip = request.client.host if request.client else "unknown"
    if not await redis_manager.check_rate_limit(client_ip, max_requests=40, window_s=1):
        raise HTTPException(
            status_code=429,
            detail="Too Many Requests: Rate limit exceeded. Please wait a moment before sending more requests.",
            headers={"Retry-After": "1"}
        )

    # Spec 019: Layer 2 Embedding Vector Cache Hit Check (US1, FR-002)
    if request.method == "POST" and clean_path in ("embeddings", "embedding"):
        try:
            body_bytes = await request.body()
            if body_bytes:
                b_data = json.loads(body_bytes)
                input_val = b_data.get("input")
                m_id = b_data.get("model", "bge-m3")
                if isinstance(input_val, str):
                    cached_vec = await redis_manager.get_embedding(m_id, input_val)
                    if cached_vec:
                        cached_payload = {
                            "object": "list",
                            "data": [{"object": "embedding", "index": 0, "embedding": cached_vec}],
                            "model": m_id,
                            "usage": {"prompt_tokens": len(input_val.split()), "total_tokens": len(input_val.split())}
                        }
                        return StreamingResponse(
                            content=iter([json.dumps(cached_payload).encode("utf-8")]),
                            media_type="application/json",
                            headers={"X-Cache": "HIT-REDIS"}
                        )
        except Exception as e:
            logger.error(f"Embedding cache check error: {e}")

    # Spec 019: Layer 3 Reranker Score Cache Hit Check (US1, FR-002)
    if request.method == "POST" and clean_path in ("rerank", "reranking"):
        try:
            body_bytes = await request.body()
            if body_bytes:
                b_data = json.loads(body_bytes)
                q_val = b_data.get("query", "")
                docs_val = b_data.get("documents", [])
                if isinstance(docs_val, list) and docs_val:
                    doc_ids = [d if isinstance(d, str) else d.get("id", str(i)) for i, d in enumerate(docs_val)]
                    cached_scores = await redis_manager.get_rerank(q_val, doc_ids)
                    if cached_scores:
                        cached_payload = {
                            "model": b_data.get("model", "bge-reranker-v2-m3"),
                            "results": cached_scores
                        }
                        return StreamingResponse(
                            content=iter([json.dumps(cached_payload).encode("utf-8")]),
                            media_type="application/json",
                            headers={"X-Cache": "HIT-REDIS"}
                        )
        except Exception as e:
            logger.error(f"Reranker cache check error: {e}")

    if clean_path in ("rerank", "reranking"):
        rerank_state = await auxiliary_manager.ensure_rerank_resident("bge-reranker-v2-m3")
        if rerank_state.status != ProcessStatusEnum.READY:
            err_detail = "Reranker model is not available. Insufficient VRAM or initialization failed."
            if rerank_state.status == ProcessStatusEnum.DISABLED:
                err_detail = f"Reranker model is disabled due to repeated crashes. ({rerank_state.error_message or ''})"
            raise HTTPException(
                status_code=503,
                detail=err_detail,
                headers={"Retry-After": "10"}
            )
    elif clean_path in ("embeddings", "embedding"):
        emb_state = await auxiliary_manager.ensure_embedding_resident("bge-m3")
        if emb_state.status != ProcessStatusEnum.READY:
            err_detail = "Embedding model is not available. Insufficient VRAM or initialization failed."
            if emb_state.status == ProcessStatusEnum.DISABLED:
                err_detail = f"Embedding model is disabled due to repeated crashes. ({emb_state.error_message or ''})"
            raise HTTPException(
                status_code=503,
                detail=err_detail,
                headers={"Retry-After": "10"}
            )

    body_content = None
    prompt_text = ""
    resolved_model = "qwen3.5-9b"
    target_port = 8089
    is_client_streaming = False

    is_llm_request = (path in ("chat/completions", "completions") or clean_path in ("chat/completions", "completions")) and request.method == "POST"

    if is_llm_request:
        body_content = await request.body()
        if not body_content:
            raise HTTPException(status_code=400, detail="Request body cannot be empty.")
        try:
            body_json = json.loads(body_content)
        except Exception as e:
            logger.error(f"JSON decode failed in LLM request: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid JSON body: {e}")

        # Authoritative Model Lookup & Invalid Model 404 Rejection (T017 / OpenAI API standard)
        raw_model = body_json.get("model") or "qwen3.5-9b"
        raw_model_str = str(raw_model).strip()
        if raw_model_str.lower() not in VALID_CHAT_MODELS:
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "message": f"The model '{raw_model_str}' does not exist or is not served.",
                        "type": "invalid_request_error",
                        "param": "model",
                        "code": "model_not_found"
                    }
                }
            )

        # T010 / US1: Chat completions messages validation (OpenAI specification: 422 if missing or invalid)
        if "chat" in path or clean_path in ("chat/completions", "completions"):
            if "messages" not in body_json or not isinstance(body_json.get("messages"), list):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": {
                            "message": "Missing required field: 'messages' must be a list.",
                            "type": "invalid_request_error",
                            "param": "messages",
                            "code": "missing_required_field"
                        }
                    }
                )

        # Dynamic port and model resolution
        mid_lower = raw_model_str.lower()
        if mid_lower in ("qwen3.5-4b", "qwen3.5-4b-instruct", "fast"):
            resolved_model = "qwen3.5-4b"
            target_port = 8088
        else:
            resolved_model = "qwen3.5-9b"
            target_port = 8089
        body_json["model"] = resolved_model

        # Context limit check
        requested_n_ctx = body_json.get("n_ctx")
        if requested_n_ctx is not None:
            llama_manager.validate_requested_context(resolved_model, int(requested_n_ctx))

        # FR-007 Item 7: Jinja2 chat template delegation (no hardcoded ChatML stops injected)
        if "stop" in body_json and isinstance(body_json["stop"], str):
            body_json["stop"] = [body_json["stop"]]

        # Parse response_format (Pilos / structured JSON compatibility)
        body_json = parse_response_format(body_json)

        # Extract prompt text for pre-queue DoS limit validation
        if "messages" in body_json and isinstance(body_json["messages"], list):
            user_msgs = [m.get("content", "") for m in body_json["messages"] if isinstance(m, dict) and m.get("role") == "user"]
            prompt_text = user_msgs[-1] if user_msgs else json.dumps(body_json["messages"], ensure_ascii=False)
        elif "prompt" in body_json:
            prompt_text = str(body_json.get("prompt"))

        try:
            # T017: Keyword argument binding to prevent argument inversion
            validate_pre_queue_prompt_limits(model_id=resolved_model, prompt=prompt_text)
        except ValueError as ve:
            logger.error(f"Pre-queue prompt validation failed: {ve}")
            raise HTTPException(status_code=400, detail=str(ve))

        # Re-serialize body
        body_content = json.dumps(body_json).encode("utf-8")
        is_client_streaming = bool(body_json.get("stream", False)) or (request.headers.get("accept") == "text/event-stream")
    else:
        target_port = _get_backend_target_port(path)

    # Candidate paths for Rerank and Embedding endpoints
    candidate_paths = [request.url.path]
    if clean_path in ("rerank", "reranking"):
        for cp in ["/reranking", "/v1/rerank", "/rerank", "/v1/reranking"]:
            if cp not in candidate_paths:
                candidate_paths.append(cp)
    elif clean_path in ("embeddings", "embedding"):
        for cp in ["/v1/embeddings", "/embeddings", "/embedding"]:
            if cp not in candidate_paths:
                candidate_paths.append(cp)

    if body_content is None and request.method in ("POST", "PUT", "PATCH"):
        body_content = await request.body()

    # ═══════════════════════════════════════════════════════════════════════════
    # Case 1: LLM Streaming Request (Zero-Buffering Passthrough & Dynamic Queue)
    # ═══════════════════════════════════════════════════════════════════════════
    if is_llm_request and is_client_streaming:
        tenant_id = request.headers.get("x-tenant-id", "default")
        session_id = request.headers.get("x-session-id", "")
        p_hash = ""
        try:
            bj = json.loads(body_content) if body_content else {}
            msgs = bj.get("messages", [])
            if msgs:
                p_hash = compute_prompt_hash(msgs)
        except Exception as e:
            logger.error(f"Error computing prompt hash: {e}")

        # T013 / T018: Zero-Wait Fast-Path Slot Bypass (0ms latency when slot is free)
        sem = gpu_queue._get_semaphore(resolved_model)
        fast_path = await try_acquire_slot_nonblocking(sem)
        if fast_path:
            ticket = await gpu_queue.create_fast_path_ticket(
                model_id=resolved_model,
                tenant_id=tenant_id,
                session_id=session_id,
                prompt_hash=p_hash,
            )
        else:
            try:
                ticket = await gpu_queue.enqueue(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    prompt_hash=p_hash,
                    messages=json.loads(body_content).get("messages", []) if body_content else [],
                    model_id=resolved_model,
                )
            except QueueFullError as e:
                raise HTTPException(
                    status_code=429,
                    detail=str(e),
                    headers={"Retry-After": "5"}
                )

        async def queued_stream_generator() -> AsyncGenerator[bytes, None]:
            """GPU 큐 통합 비동기 SSE 스트리밍 제너레이터 (Zero-Buffering Passthrough)."""
            first_chunk_received = False
            ttft_ms = 0.0
            start_time = time.perf_counter()
            completion_tokens = 0
            disconnect_monitor = asyncio.create_task(_monitor_disconnect(request, ticket))
            custom_event = request.headers.get("x-queue-progress", "").lower() in ("true", "1", "yes")

            try:
                if not fast_path:
                    slot_acquired = asyncio.Event()

                    async def _wait_for_slot():
                        result = await gpu_queue.acquire_slot(ticket)
                        if result:
                            slot_acquired.set()

                    slot_task = asyncio.create_task(_wait_for_slot())

                    # 1. 큐 대기 중 SSE 이벤트 스트리밍 (queue_status + keepalive)
                    async for sse_event in gpu_queue.stream_queue_events(ticket, custom_event=custom_event):
                        yield sse_event.encode("utf-8")
                        if slot_acquired.is_set():
                            break
                        if ticket.cancel_event.is_set():
                            break

                    if not slot_acquired.is_set():
                        try:
                            await asyncio.wait_for(slot_task, timeout=1.0)
                        except asyncio.TimeoutError:
                            pass

                    if not slot_acquired.is_set() or ticket.state != QueueStateEnum.ACTIVE:
                        return

                # 2. 슬롯 획득 후 백엔드 LLM 엔진으로 HTTP 요청 전송
                client = _get_http_client(request)
                headers = [(k, v) for k, v in request.headers.raw if k.lower() not in (b"host", b"content-length", b"connection")]
                headers.append((b"connection", b"close"))
                backend_url = f"http://127.0.0.1:{target_port}{candidate_paths[0]}"
                if request.url.query:
                    backend_url += f"?{request.url.query}"

                req = client.build_request(
                    request.method,
                    backend_url,
                    headers=headers,
                    content=body_content
                )
                try:
                    r_backend = await client.send(req, stream=True)
                except Exception as e:
                    logger.error(f"Backend LLM connection failed on port {target_port}: {e}")
                    yield f"data: {json.dumps({'error': f'Backend LLM connection failed: {e}'})}\n\n".encode("utf-8")
                    return

                if r_backend.status_code != 200:
                    err_msg = await r_backend.aread()
                    await r_backend.aclose()
                    logger.error(f"Backend LLM returned status {r_backend.status_code}: {err_msg.decode('utf-8', errors='ignore')}")
                    yield f"data: {json.dumps({'error': err_msg.decode('utf-8', errors='ignore')})}\n\n".encode("utf-8")
                    return

                # 3. 백엔드 스트림 청크 전달 (Lightweight Passthrough)
                try:
                    async for chunk in r_backend.aiter_raw():
                        if not first_chunk_received:
                            ttft_ms = (time.perf_counter() - start_time) * 1000.0
                            first_chunk_received = True
                        if await request.is_disconnected():
                            await r_backend.aclose()
                            break
                        completion_tokens += 1
                        yield chunk
                finally:
                    await r_backend.aclose()
                    total_latency_s = time.perf_counter() - start_time
                    tps = round(completion_tokens / max(total_latency_s, 0.05), 1) if completion_tokens else 0.0

                    auth_header = request.headers.get("authorization", "")
                    raw_key = auth_header.replace("Bearer ", "").strip() if "Bearer " in auth_header else "anonymous"
                    masked_key = raw_key[:7] + "..." + raw_key[-4:] if len(raw_key) > 12 else raw_key

                    try:
                        from src.core.metrics_db import metrics_db
                        prompt_tokens = max(1, len(prompt_text) // 4)
                        await anyio.to_thread.run_sync(
                            lambda: metrics_db.log_request(
                                api_key=masked_key,
                                endpoint=request.url.path,
                                status_code=r_backend.status_code,
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                                ttft_ms=round(ttft_ms, 2),
                                tps=tps,
                                is_error=(r_backend.status_code >= 400),
                                prompt_text=prompt_text[:500],
                                completion_text="[STREAMING_PASSTHROUGH]",
                                thinking_text=None
                            )
                        )
                    except Exception as ex:
                        logger.error(f"Error asynchronously logging streaming metrics: {ex}")

            finally:
                await gpu_queue.release_slot(ticket)
                disconnect_monitor.cancel()
                try:
                    await disconnect_monitor
                except asyncio.CancelledError:
                    pass

        response_headers = {
            "content-type": "text/event-stream",
            "cache-control": "no-cache, no-transform",
            "x-accel-buffering": "no",
            "connection": "keep-alive",
            "x-model-served": resolved_model,
        }
        return StreamingResponse(
            queued_stream_generator(),
            status_code=200,
            headers=response_headers
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Case 2: LLM Non-Streaming Request (Mandatory Pre-Dispatch Slot Acquisition)
    # ═══════════════════════════════════════════════════════════════════════════
    if is_llm_request and not is_client_streaming:
        tenant_id = request.headers.get("x-tenant-id", "default")
        session_id = request.headers.get("x-session-id", "")
        p_hash = ""
        try:
            bj = json.loads(body_content) if body_content else {}
            msgs = bj.get("messages", [])
            if msgs:
                p_hash = compute_prompt_hash(msgs)
        except Exception as e:
            logger.error(f"Error computing prompt hash for non-streaming: {e}")

        # T013 / T018: Zero-Wait Fast-Path Slot Bypass
        sem = gpu_queue._get_semaphore(resolved_model)
        fast_path = await try_acquire_slot_nonblocking(sem)
        if fast_path:
            ticket = await gpu_queue.create_fast_path_ticket(
                model_id=resolved_model,
                tenant_id=tenant_id,
                session_id=session_id,
                prompt_hash=p_hash,
            )
        else:
            try:
                ticket = await gpu_queue.enqueue(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    prompt_hash=p_hash,
                    messages=json.loads(body_content).get("messages", []) if body_content else [],
                    model_id=resolved_model,
                )
            except QueueFullError as e:
                raise HTTPException(
                    status_code=429,
                    detail=str(e),
                    headers={"Retry-After": "5"}
                )

            # Acquire slot BEFORE dispatching backend HTTP request (FR-070, Eliminates 17.7GB CUDA OOM)
            slot_acquired = await gpu_queue.acquire_slot(ticket)
            if not slot_acquired or ticket.state != QueueStateEnum.ACTIVE:
                await gpu_queue.release_slot(ticket)
                raise HTTPException(
                    status_code=503,
                    detail="Failed to acquire GPU inference slot. The queue may be full or ticket was cancelled.",
                    headers={"Retry-After": "5"}
                )

        start_time = time.perf_counter()
        client = _get_http_client(request)
        headers = [(k, v) for k, v in request.headers.raw if k.lower() not in (b"host", b"content-length", b"connection")]
        headers.append((b"connection", b"close"))
        backend_url = f"http://127.0.0.1:{target_port}{candidate_paths[0]}"
        if request.url.query:
            backend_url += f"?{request.url.query}"

        r = None
        try:
            req = client.build_request(
                request.method,
                backend_url,
                headers=headers,
                content=body_content
            )
            r = await client.send(req, stream=False)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException) as e:
            logger.error(f"Backend LLM connection/timeout error on port {target_port}: {e}")
            raise HTTPException(
                status_code=503,
                detail=f"Model server at port {target_port} is unreachable or timed out.",
                headers={"Retry-After": "5"}
            )
        except Exception as e:
            logger.error(f"Backend LLM dispatch error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            await gpu_queue.release_slot(ticket)

        total_latency_s = time.perf_counter() - start_time
        resp_bytes = r.content
        prompt_tokens = 0
        completion_tokens = 0
        completion_text = ""
        thinking_text = None

        try:
            resp_json = r.json()
            if isinstance(resp_json, dict):
                usage = resp_json.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                choices = resp_json.get("choices", [])
                if choices and isinstance(choices[0], dict):
                    completion_text = choices[0].get("message", {}).get("content", "")
                    if completion_text:
                        from src.core.think_tag_parser import parse_think_tags
                        completion_text, thinking_text = parse_think_tags(completion_text)
        except Exception as e:
            logger.error(f"Error parsing backend JSON response: {e}")

        tps = round(completion_tokens / max(total_latency_s, 0.05), 1) if completion_tokens else 0.0
        auth_header = request.headers.get("authorization", "")
        raw_key = auth_header.replace("Bearer ", "").strip() if "Bearer " in auth_header else "anonymous"
        masked_key = raw_key[:7] + "..." + raw_key[-4:] if len(raw_key) > 12 else raw_key

        try:
            from src.core.metrics_db import metrics_db
            await anyio.to_thread.run_sync(
                lambda: metrics_db.log_request(
                    api_key=masked_key,
                    endpoint=request.url.path,
                    status_code=r.status_code,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    ttft_ms=round(total_latency_s * 1000.0, 2),
                    tps=tps,
                    is_error=(r.status_code >= 400),
                    prompt_text=prompt_text[:500],
                    completion_text=completion_text[:500],
                    thinking_text=thinking_text
                )
            )
        except Exception as ex:
            logger.error(f"Error asynchronously logging non-streaming metrics: {ex}")

        excluded_headers = {"content-length", "transfer-encoding", "connection", "content-encoding"}
        response_headers = {
            k: v for k, v in r.headers.items()
            if k.lower() not in excluded_headers
        }
        response_headers["x-model-served"] = resolved_model

        return StreamingResponse(
            content=iter([resp_bytes]),
            status_code=r.status_code,
            headers=response_headers,
            media_type=r.headers.get("content-type", "application/json")
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Case 3: Non-LLM Request (Embedding, Reranker, etc.)
    # ═══════════════════════════════════════════════════════════════════════════
    # FR-007 Item 1: Pilos model auto-injection for /v1/embeddings and /v1/rerank
    if clean_path in ("embeddings", "embedding"):
        target_port = 8090
        try:
            if body_content:
                b_json = json.loads(body_content)
                if not b_json.get("model"):
                    b_json["model"] = "bge-m3"
                    body_content = json.dumps(b_json).encode("utf-8")
                inp = b_json.get("input", "")
                inp_str = " ".join(inp) if isinstance(inp, list) else str(inp)
                validate_pre_queue_prompt_limits(model_id="bge-m3", prompt=inp_str)
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Embedding pre-check warning: {e}")
    elif clean_path in ("rerank", "reranking"):
        target_port = 8091
        try:
            if body_content:
                b_json = json.loads(body_content)
                if not b_json.get("model"):
                    b_json["model"] = "bge-reranker-v2-m3"
                    body_content = json.dumps(b_json).encode("utf-8")
                q = b_json.get("query", "")
                docs = b_json.get("documents", [])
                docs_str = " ".join([d if isinstance(d, str) else d.get("text", "") for d in docs])
                validate_pre_queue_prompt_limits(model_id="bge-reranker-v2-m3", prompt=f"{q} {docs_str}")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Reranker pre-check warning: {e}")

    client = _get_http_client(request)
    # FR-007 Item 2: Ingress Connection: close header injection for backend calls
    headers = [(k, v) for k, v in request.headers.raw if k.lower() not in (b"host", b"content-length", b"connection")]
    headers.append((b"connection", b"close"))

    r = None
    for cand_path in candidate_paths:
        backend_url = f"http://127.0.0.1:{target_port}{cand_path}"
        if request.url.query:
            backend_url += f"?{request.url.query}"

        try:
            req = client.build_request(
                request.method,
                backend_url,
                headers=headers,
                content=body_content if body_content is not None else request.stream()
            )
            r = await client.send(req, stream=True)
            if r.status_code == 404 and len(candidate_paths) > 1 and cand_path != candidate_paths[-1]:
                await r.aclose()
                continue
            if r.status_code == 503:
                await r.aclose()
                raise HTTPException(
                    status_code=503,
                    detail=f"Model server at port {target_port} is currently initializing. Please try again in a few seconds.",
                    headers={"Retry-After": "5"}
                )
            break
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException):
            if cand_path != candidate_paths[-1]:
                continue
            raise HTTPException(
                status_code=503,
                detail=f"Model server at port {target_port} is currently unreachable or loading. Please try again in a few seconds.",
                headers={"Retry-After": "5"}
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error forwarding non-LLM request: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    if r is None:
        raise HTTPException(
            status_code=503,
            detail=f"Model server at port {target_port} is unreachable.",
            headers={"Retry-After": "5"}
        )

    # T015 / T016 / FR-007 Item 3: Direct C++ /v1/rerank relay with dual mapping (results -> data)
    if clean_path in ("rerank", "reranking") and r.status_code == 200:
        resp_bytes = await r.aread()
        await r.aclose()
        try:
            res_json = json.loads(resp_bytes)
            res_json = normalize_rerank_response(res_json)
            resp_bytes = json.dumps(res_json, ensure_ascii=False).encode("utf-8")
        except Exception as ex:
            logger.warning(f"Could not normalize rerank response: {ex}")

        excluded_headers = {"content-length", "transfer-encoding", "connection", "content-encoding"}
        response_headers = {
            k: v for k, v in r.headers.items()
            if k.lower() not in excluded_headers
        }
        response_headers["content-length"] = str(len(resp_bytes))
        return StreamingResponse(
            content=iter([resp_bytes]),
            status_code=r.status_code,
            headers=response_headers,
            media_type="application/json"
        )

    async def non_llm_stream_generator() -> AsyncGenerator[bytes, None]:
        """Non-LLM 스트리밍 제너레이터."""
        try:
            async for chunk in r.aiter_raw():
                # FR-007 Item 4: Client disconnect triggers backend socket close immediately
                if await request.is_disconnected():
                    await r.aclose()
                    break
                yield chunk
        finally:
            await r.aclose()

    excluded_headers = {"content-length", "transfer-encoding", "connection", "content-encoding"}
    response_headers = {
        k: v for k, v in r.headers.items()
        if k.lower() not in excluded_headers
    }

    return StreamingResponse(
        non_llm_stream_generator(),
        status_code=r.status_code,
        headers=response_headers
    )


async def _monitor_disconnect(request: Request, ticket) -> None:
    """Spec 031 FR-008: 클라이언트 연결 끊김을 비동기로 감시하고 큐에서 즉시 Purge."""
    try:
        while True:
            if await request.is_disconnected():
                await gpu_queue.disconnect_ticket(ticket.ticket_id)
                break
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        pass
