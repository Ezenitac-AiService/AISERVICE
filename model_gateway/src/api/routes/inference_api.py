"""
OpenAI-compatible inference routing and proxy handlers (FR-001, FR-005, FR-007, FR-009).
Provides GET /v1/models catalog listing and reverse-proxying for RAG/Agent requests.
"""

import os
import sys
import time
import json
import math
import asyncio
from typing import Any, AsyncGenerator
import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from src.core.llama_manager import llama_manager
from src.core.auxiliary_manager import auxiliary_manager
from src.core.config_manager import ConfigManager
from src.core.model_downloader import ModelDownloader
from src.core.process_manager import ProcessStatusEnum
from src.core.client_logger import get_client_logger
from src.core.scheduler import priority_scheduler
from src.core.redis_manager import redis_manager
from src.core.queue_manager import gpu_queue, QueueFullError
from src.core.queue_models import QueueStateEnum, compute_prompt_hash


router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# Spec 031: GPU Queue Management Endpoints (FR-008, FR-009)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/v1/queue/cancel")
async def cancel_queue_request(request: Request) -> dict:
    """Spec 031 FR-008: 대기 중인 요청을 명시적으로 취소하고 큐에서 즉시 Purge."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    ticket_id = body.get("ticket_id", "")
    if not ticket_id:
        raise HTTPException(status_code=400, detail="ticket_id is required.")

    success = await gpu_queue.cancel_ticket(ticket_id)
    if success:
        return {
            "status": "CANCELLED",
            "ticket_id": ticket_id,
            "message": "Request successfully purged from GPU queue."
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Ticket '{ticket_id}' not found or already completed."
        )


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
    except Exception:
        return 8089, "127.0.0.1"


_port, _host = _get_llama_server_config()
LLAMA_SERVER_PORT = _port
LLAMA_SERVER_URL = f"http://{_host}:{LLAMA_SERVER_PORT}"


def _build_default_client() -> httpx.AsyncClient:
    """FR-005 & FR-009: 커넥션 풀 설정을 config/server_config.json에서 동적 로드하여 싱글톤 구성."""
    try:
        cm = ConfigManager()
        server_cfg = cm.get_server_config()
        pool_cfg = server_cfg.get("connection_pool", {})
        max_keepalive = pool_cfg.get("max_keepalive_connections", 20)
        max_conn = pool_cfg.get("max_connections", 100)
    except Exception:
        max_keepalive = 20
        max_conn = 100

    return httpx.AsyncClient(
        base_url=LLAMA_SERVER_URL,
        limits=httpx.Limits(max_keepalive_connections=max_keepalive, max_connections=max_conn),
        timeout=None
    )


_default_client = _build_default_client()


def parse_response_format(body: dict[str, Any]) -> dict[str, Any]:
    """FR-002: OpenAI OpenAI response_format 파라미터를 파싱하여 llama-server 문법 규격으로 변환."""
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
    """Check if the backend LLM engine is ready to accept requests."""
    if os.environ.get("MOCK_LLAMA_SERVER") == "1":
        return True
    if llama_manager.process_manager.state.status == ProcessStatusEnum.UNLOADED:
        return False
    return llama_manager.is_ready()


def _get_http_client(request: Request) -> httpx.AsyncClient:
    """Helper to retrieve singleton AsyncClient from app.state or fallback."""
    if hasattr(request.app.state, "http_client") and request.app.state.http_client:
        return request.app.state.http_client
    return _default_client


@router.get("/v1/models")
async def list_models(request: Request) -> dict[str, Any]:
    """FR-001 & FR-007 & Spec 033: OpenAI API 표준 GET /v1/models 동적 모델 카탈로그 엔드포인트.
    
    ConfigManager 기반 전체 지원 모델 정보, 다운로드 상태, 현재 활성화 여부 및 16K 컨텍스트를
    OpenAI 규격 JSON ({"object": "list", "data": [...]})으로 동적 반환합니다.
    """
    cm = ConfigManager()
    catalog = cm.get_model_catalog()
    downloader = ModelDownloader(config_manager=cm)
    
    current_model = None
    current_n_ctx = 16384
    try:
        cfg = llama_manager.config_manager.get_config()
        current_model = cfg.get("current_model", "qwen3.5-2b")
        current_n_ctx = int(cfg.get("current_n_ctx", 16384))
    except Exception:
        pass

    created_ts = int(time.time())
    models_data = []
    for model_id, entry in catalog.items():
        is_available = downloader.is_model_available(model_id)
        is_active = (current_model == model_id and llama_manager.is_ready())
        is_resident = (current_model == model_id)
        models_data.append({
            "id": model_id,
            "object": "model",
            "created": created_ts,
            "owned_by": "llm-server",
            "permission": [],
            "is_available": is_available,
            "is_active": is_active,
            "is_resident": is_resident,
            "current_n_ctx": current_n_ctx if is_active else entry.get("context_window", 16384),
        })

    # Always ensure resident helper models are visible
    for aux_id in ("bge-m3", "bge-reranker-v2-m3"):
        if not any(m["id"] == aux_id for m in models_data):
            models_data.append({
                "id": aux_id,
                "object": "model",
                "created": created_ts,
                "owned_by": "auxiliary-server",
                "permission": [],
                "is_available": True,
                "is_active": True,
                "is_resident": True,
                "current_n_ctx": 8192,
            })

    return {"object": "list", "data": models_data}


@router.get("/v1/profile")
async def get_profile(request: Request) -> dict[str, Any]:
    """Spec 033 & Spec 034 & Spec 036: 3-Axis Decoupled Hardware & Active Resident Model Profile Endpoint."""
    cm = ConfigManager()
    current_model = cm.get_default_model()
    current_n_ctx = cm.get_current_n_ctx()
    try:
        cfg = llama_manager.config_manager.get_config()
        current_model = cfg.get("current_model", current_model)
        current_n_ctx = int(cfg.get("current_n_ctx", current_n_ctx))
    except Exception:
        pass

    from src.core.gpu_detector import detect_hardware_capabilities
    hardware_profile = detect_hardware_capabilities()
    
    return {
        "status": "healthy",
        "active_model": current_model if llama_manager.is_ready() else cm.get_default_model(),
        "current_n_ctx": current_n_ctx,
        "dynamic_n_ctx_max": hardware_profile.dynamic_n_ctx,
        "hardware_tier": hardware_profile.hardware_tier.value,
        "serving_strategy": {
            "resident_model": hardware_profile.recommended_model,
            "resident_standard_n_ctx": hardware_profile.resident_standard_n_ctx,
            "resident_ultra_n_ctx": hardware_profile.resident_ultra_n_ctx,
            "batch_model": hardware_profile.recommended_batch_model,
            "batch_n_ctx": hardware_profile.batch_n_ctx,
            "min_target_tps": hardware_profile.min_target_tps,
        },
        "hardware": hardware_profile.model_dump(),
        "vram_total_mb": hardware_profile.total_vram_mb,
        "vram_used_mb": max(0, hardware_profile.total_vram_mb - hardware_profile.free_vram_mb),
        "single_model_mode": os.getenv("SINGLE_MODEL_MODE", "true").lower() in ("1", "true", "yes"),
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
            "resident_model": hw.recommended_model,
            "resident_standard_n_ctx": hw.resident_standard_n_ctx,
            "resident_ultra_n_ctx": hw.resident_ultra_n_ctx,
            "batch_model": hw.recommended_batch_model,
            "batch_n_ctx": hw.batch_n_ctx,
            "min_target_tps": hw.min_target_tps,
            "dynamic_n_ctx_max": hw.dynamic_n_ctx,
        },
    }


def _get_backend_target_port(path: str) -> int:
    try:
        cm = ConfigManager()
        server_cfg = cm.get_server_config()
        clean_path = path.strip("/").split("/")[-1]
        if clean_path in ("embeddings", "embedding"):
            return server_cfg.get("embedding_backend_port", 8090)
        elif clean_path in ("rerank", "reranking"):
            return server_cfg.get("rerank_backend_port", 8091)
        else:
            return server_cfg.get("backend_port", 8089)
    except Exception:
        clean_path = path.strip("/").split("/")[-1]
        if clean_path in ("embeddings", "embedding"):
            return 8090
        elif clean_path in ("rerank", "reranking"):
            return 8091
        return 8089


@router.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
@router.api_route("/embedding", methods=["POST", "OPTIONS"])
@router.api_route("/v1/embedding", methods=["POST", "OPTIONS"])
@router.api_route("/rerank", methods=["POST", "OPTIONS"])
@router.api_route("/v1/rerank", methods=["POST", "OPTIONS"])
async def reverse_proxy(request: Request, path: str = "") -> StreamingResponse:
    """FR-009 & FR-002: RAG, Agent, Embedding, Reranker 요청을 백엔드 싱글톤 인스턴스로 역방향 프록시 라우팅."""
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
        except Exception:
            pass

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
        except Exception:
            pass

    # FR-005: 25MB Body limit check for 32GB RAM / 11GB VRAM server defense before processing
    MAX_PAYLOAD_BYTES = 25 * 1024 * 1024
    if request.method == "POST" and clean_path in ("chat/completions", "completions"):
        body_bytes = await request.body()
        if body_bytes and len(body_bytes) > MAX_PAYLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Payload Too Large: Request body exceeds maximum allowed size of 25MB."
            )

    if clean_path in ("rerank", "reranking"):
        rerank_state = await auxiliary_manager.ensure_rerank_resident("bge-reranker-v2-m3")
        if rerank_state.status != ProcessStatusEnum.READY:
            err_detail = "Reranker model is not available. The model may have failed to load due to insufficient VRAM."
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
            err_detail = "Embedding model is not available. The model may have failed to load due to insufficient VRAM."
            if emb_state.status == ProcessStatusEnum.DISABLED:
                err_detail = f"Embedding model is disabled due to repeated crashes. ({emb_state.error_message or ''})"
            raise HTTPException(
                status_code=503,
                detail=err_detail,
                headers={"Retry-After": "10"}
            )

    # Mock response support for pytest/offline execution
    if os.environ.get("MOCK_LLAMA_SERVER") == "1":
        if clean_path in ("embeddings", "embedding"):

            mock_data = {
                "object": "list",
                "data": [{"object": "embedding", "index": 0, "embedding": [0.01] * 1024}],
                "model": "bge-m3",
                "usage": {"prompt_tokens": 10, "total_tokens": 10}
            }
            return StreamingResponse(content=iter([json.dumps(mock_data).encode("utf-8")]), media_type="application/json")
        elif clean_path in ("rerank", "reranking"):
            mock_data = {
                "model": "bge-reranker-v2-m3",
                "results": [
                    {"index": 0, "relevance_score": 0.95},
                    {"index": 1, "relevance_score": 0.12}
                ]
            }
            return StreamingResponse(content=iter([json.dumps(mock_data).encode("utf-8")]), media_type="application/json")
        elif clean_path in ("chat/completions", "completions"):
            cm = ConfigManager()
            mock_model = cm.get_default_model()
            try:
                raw_body = await request.body()
                if raw_body:
                    b_json = json.loads(raw_body)
                    if b_json.get("model"):
                        mock_model = b_json.get("model")
            except Exception:
                pass

            mock_data = {
                "id": "chatcmpl-mock123",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": mock_model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "안녕하세요! 무엇을 도와드릴까요?"},
                        "finish_reason": "stop"
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
            }
            return StreamingResponse(content=iter([json.dumps(mock_data).encode("utf-8")]), media_type="application/json")


    MAX_PAYLOAD_BYTES = 25 * 1024 * 1024  # 25MB Body limit for 32GB RAM / 11GB VRAM server defense (FR-005)
    body_content = None
    prompt_text = None
    is_client_streaming = (request.headers.get("accept") == "text/event-stream")
    if request.method == "POST" and clean_path in ("chat/completions", "completions"):
        body_content = await request.body()
        if body_content and len(body_content) > MAX_PAYLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Payload Too Large: Request body exceeds maximum allowed size of 25MB."
            )
        if body_content:
            try:
                body_json = json.loads(body_content)
                if "stream" in body_json:
                    is_client_streaming = bool(body_json.get("stream", False))

                model_id = body_json.get("model") or llama_manager.config_manager.get_default_model()
                priority = body_json.get("priority") or body_json.get("extra_body", {}).get("priority", "high")
                requested_n_ctx = body_json.get("n_ctx")
                if requested_n_ctx is not None:
                    llama_manager.validate_requested_context(model_id, int(requested_n_ctx))

                # FR-001, FR-002, FR-007: Configurable Serving Mode (Single Model 2B vs Multi-Model Hot-Swap)
                single_model_mode = os.getenv("SINGLE_MODEL_MODE", "true").lower() in ("1", "true", "yes")
                current_model = llama_manager.process_manager.state.model_id
                llama_manager.touch_activity()

                if single_model_mode:
                    # 8GB VRAM 최적화 단일 상주 모드: 프로세스 킬/스와핑 핑퐁 원천 차단
                    resident_model = llama_manager.config_manager.get_default_model()
                    if model_id != resident_model:
                        model_id = resident_model
                        body_json["model"] = resident_model
                        body_content = json.dumps(body_json).encode("utf-8")
                    if not llama_manager.is_ready() and os.environ.get("MOCK_LLAMA_SERVER") != "1":
                        n_ctx = int(requested_n_ctx) if requested_n_ctx is not None else int(llama_manager.config_manager.get_config().get("current_n_ctx", 16384))
                        await llama_manager.load_model_with_download(resident_model, n_ctx=n_ctx)
                else:
                    # 고용량 VRAM(24GB+) 마이그레이션 환경: 다중 모델 핫스왑 경로 100% 보존
                    if model_id and current_model and model_id != current_model and os.environ.get("MOCK_LLAMA_SERVER") != "1":
                        n_ctx = int(requested_n_ctx) if requested_n_ctx is not None else (16384 if "2b" in model_id.lower() else (12288 if "4b" in model_id.lower() else 4096))
                        state = await llama_manager.load_model_with_download(model_id, n_ctx=n_ctx)
                        if state.status != ProcessStatusEnum.READY:
                            if "2b" not in model_id.lower():
                                print(f"[InferenceAPI] Warning: Model '{model_id}' failed to load ({state.error_message}). Executing instant 2B fallback...")
                                fallback_state = await llama_manager.load_model_with_download("qwen3.5-2b", n_ctx=16384)
                                model_id = "qwen3.5-2b"
                                body_json["model"] = "qwen3.5-2b"
                                body_content = json.dumps(body_json).encode("utf-8")
                            else:
                                raise HTTPException(
                                    status_code=503,
                                    detail=f"Failed to switch model to '{model_id}': {state.error_message or 'Model load timeout or VRAM limit exceeded.'}",
                                    headers={"Retry-After": "10"}
                                )

                if "messages" in body_json and isinstance(body_json["messages"], list):
                    user_msgs = [m.get("content", "") for m in body_json["messages"] if isinstance(m, dict) and m.get("role") == "user"]
                    prompt_text = user_msgs[-1] if user_msgs else json.dumps(body_json["messages"], ensure_ascii=False)
                elif "prompt" in body_json:
                    prompt_text = str(body_json.get("prompt"))

                # Spec 018 / T011: Guided JSON schema and grammar constrained decoding
                body_json = parse_response_format(body_json)
                body_content = json.dumps(body_json).encode("utf-8")
            except HTTPException:
                raise
            except Exception:
                pass


    target_port = _get_backend_target_port(path)
    
    # Candidate path resolution for Rerank and Embedding endpoints (FR-001 & FR-002)
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

    is_llm_request = (path in ("chat/completions", "completions") or clean_path in ("chat/completions", "completions")) and request.method == "POST"

    # Spec 031: LLM SSE 스트리밍 요청에 대해 가변 슬롯 큐 및 즉시 응답 적용
    if is_llm_request and is_client_streaming:
        tenant_id = request.headers.get("x-tenant-id", "default")
        session_id = request.headers.get("x-session-id", "")
        p_hash = ""
        if body_content:
            try:
                bj = json.loads(body_content)
                msgs = bj.get("messages", [])
                if msgs:
                    p_hash = compute_prompt_hash(msgs)
            except Exception:
                pass

        try:
            ticket = await gpu_queue.enqueue(
                tenant_id=tenant_id,
                session_id=session_id,
                prompt_hash=p_hash,
                messages=json.loads(body_content).get("messages", []) if body_content else [],
            )
        except QueueFullError as e:
            raise HTTPException(
                status_code=429,
                detail=str(e),
                headers={"Retry-After": "5"}
            )

        async def queued_stream_generator() -> AsyncGenerator[bytes, None]:
            """Spec 031: GPU 큐 통합 비동기 SSE 스트리밍 제너레이터."""
            first_chunk_received = False
            ttft_ms = 0.0
            start_time = time.perf_counter()
            captured_chunks = []
            disconnect_monitor = asyncio.create_task(_monitor_disconnect(request, ticket))

            try:
                slot_acquired = asyncio.Event()

                async def _wait_for_slot():
                    result = await gpu_queue.acquire_slot(ticket)
                    if result:
                        slot_acquired.set()

                slot_task = asyncio.create_task(_wait_for_slot())

                # 1. 큐 대기 중 SSE 이벤트 스트리밍 (queue_status + 15초 keepalive)
                async for sse_event in gpu_queue.stream_queue_events(ticket):
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

                # 2. 슬롯 획득 후 백엔드 LLM 엔진(port 8089)으로 HTTP 요청 전송
                client = _get_http_client(request)
                headers = [(k, v) for k, v in request.headers.raw if k.lower() not in (b"host", b"content-length")]
                backend_url = f"http://127.0.0.1:{target_port}{candidate_paths[0]}"
                if request.url.query:
                    backend_url += f"?{request.url.query}"

                req = client.build_request(
                    request.method,
                    backend_url,
                    headers=headers,
                    content=body_content if body_content is not None else request.stream()
                )
                try:
                    r_backend = await client.send(req, stream=True)
                except Exception as e:
                    yield f"data: {json.dumps({'error': f'Backend LLM connection failed: {e}'})}\n\n".encode("utf-8")
                    return

                if r_backend.status_code != 200:
                    err_msg = await r_backend.aread()
                    await r_backend.aclose()
                    yield f"data: {json.dumps({'error': err_msg.decode('utf-8', errors='ignore')})}\n\n".encode("utf-8")
                    return

                # 3. 백엔드 스트림 청크 전달
                async def _execute_stream_inner():
                    nonlocal first_chunk_received, ttft_ms
                    try:
                        async for chunk in r_backend.aiter_raw():
                            if not first_chunk_received:
                                ttft_ms = (time.perf_counter() - start_time) * 1000.0
                                first_chunk_received = True
                            if await request.is_disconnected():
                                break
                            captured_chunks.append(chunk)
                            yield chunk
                    finally:
                        await r_backend.aclose()
                        try:
                            completion_text = ""
                            prompt_tokens = 0
                            completion_tokens = 0
                            if captured_chunks:
                                full_resp = b"".join(captured_chunks).decode("utf-8", errors="ignore")
                                if full_resp.strip().startswith("{"):
                                    res_json = json.loads(full_resp)
                                    choices = res_json.get("choices", [])
                                    if choices:
                                        completion_text = choices[0].get("message", {}).get("content", "") or choices[0].get("text", "")
                                    usage = res_json.get("usage", {})
                                    prompt_tokens = usage.get("prompt_tokens", 0)
                                    completion_tokens = usage.get("completion_tokens", 0)
                                else:
                                    for line in full_resp.splitlines():
                                        line = line.strip()
                                        if line.startswith("data: ") and line != "data: [DONE]":
                                            try:
                                                c_json = json.loads(line[6:])
                                                choices = c_json.get("choices", [])
                                                if choices:
                                                    delta = choices[0].get("delta", {})
                                                    content = delta.get("content", "")
                                                    if content:
                                                        completion_text += content
                                            except Exception:
                                                pass
                            thinking_text = None
                            if completion_text:
                                from src.core.think_tag_parser import parse_think_tags
                                clean_text, think_text = parse_think_tags(completion_text)
                                completion_text = clean_text
                                thinking_text = think_text

                            total_latency_s = time.perf_counter() - start_time
                            tps = round(completion_tokens / max(total_latency_s, 0.05), 1) if completion_tokens else 0.0
                            llama_manager.process_manager.record_tps_sample(tps)

                            auth_header = request.headers.get("authorization", "")
                            api_key = auth_header.replace("Bearer ", "").strip() if "Bearer " in auth_header else "anonymous"

                            from src.core.metrics_db import metrics_db
                            metrics_db.log_request(
                                api_key=api_key or "anonymous",
                                endpoint=request.url.path,
                                status_code=r_backend.status_code,
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                                ttft_ms=round(ttft_ms, 2),
                                tps=tps,
                                is_error=(r_backend.status_code >= 400),
                                prompt_text=prompt_text,
                                completion_text=completion_text,
                                thinking_text=thinking_text
                            )
                        except Exception:
                            pass

                async for item in _execute_stream_inner():
                    yield item

            finally:
                if ticket.state == QueueStateEnum.ACTIVE:
                    await gpu_queue.release_slot(ticket)
                disconnect_monitor.cancel()
                try:
                    await disconnect_monitor
                except asyncio.CancelledError:
                    pass

        response_headers = {
            "content-type": "text/event-stream",
            "cache-control": "no-cache",
            "x-accel-buffering": "no",
            "x-model-served": model_id,
        }
        return StreamingResponse(
            queued_stream_generator(),
            status_code=200,
            headers=response_headers
        )

    # Non-LLM 또는 Non-Streaming 요청 처리 (Embedding, Reranker 등)
    client = _get_http_client(request)
    headers = [(k, v) for k, v in request.headers.raw if k.lower() not in (b"host", b"content-length")]
    
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
            if target_port == LLAMA_SERVER_PORT:
                current_model = llama_manager.config_manager.get_default_model()
                asyncio.create_task(llama_manager.ensure_default_model_resident(current_model))
            raise HTTPException(
                status_code=503,
                detail=f"Model server at port {target_port} is currently unreachable or loading. Please try again in a few seconds.",
                headers={"Retry-After": "5"}
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    if r is None:
        raise HTTPException(
            status_code=503,
            detail=f"Model server at port {target_port} is unreachable.",
            headers={"Retry-After": "5"}
        )

    if r.status_code == 404 and clean_path in ("rerank", "reranking"):
        # Fallback adapter for Python llama_cpp.server on port 8091 which only exposes /v1/embeddings
        await r.aclose()
        try:
            body_json = json.loads(body_content) if body_content else {}
            query = body_json.get("query") or body_json.get("prompt") or ""
            documents = body_json.get("documents") or body_json.get("texts") or []

            if query and documents:
                emb_url = f"http://127.0.0.1:{target_port}/v1/embeddings"
                emb_payload = {"input": [query] + documents}
                async with httpx.AsyncClient() as adapter_client:
                    emb_resp = await adapter_client.post(emb_url, json=emb_payload, timeout=10.0)
                if emb_resp.status_code == 200:
                    emb_data = emb_resp.json().get("data", [])
                    if len(emb_data) == len(documents) + 1:
                        def cosine_sim(a, b):
                            if a and isinstance(a[0], list):
                                a = a[0]
                            if b and isinstance(b[0], list):
                                b = b[0]
                            dot = sum(float(x) * float(y) for x, y in zip(a, b))
                            norm_a = math.sqrt(sum(float(x) * float(x) for x in a))
                            norm_b = math.sqrt(sum(float(y) * float(y) for y in b))
                            return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0

                        query_vec = emb_data[0]["embedding"]
                        doc_vecs = [item["embedding"] for item in emb_data[1:]]

                        results = []
                        for idx, doc_vec in enumerate(doc_vecs):
                            score = cosine_sim(query_vec, doc_vec)
                            results.append({"index": idx, "relevance_score": round(score, 6)})

                        results.sort(key=lambda x: x["relevance_score"], reverse=True)
                        rerank_response = {
                            "object": "list",
                            "data": results,
                            "results": results,
                            "usage": {"prompt_tokens": len(query.split()), "total_tokens": len(query.split())}
                        }
                        resp_bytes = json.dumps(rerank_response, ensure_ascii=False).encode("utf-8")
                        return StreamingResponse(content=iter([resp_bytes]), media_type="application/json")
        except Exception as ex:
            import traceback
            from src.core.process_manager import ProcessManager
            bin_info = ProcessManager.verify_and_build_llama_server()
            binary_mode = bin_info.build_source
            pm = auxiliary_manager.rerank_pm if hasattr(auxiliary_manager, "rerank_pm") else None
            pid = pm.process.pid if (pm and pm.process) else None
            is_alive = (pm.process.returncode is None) if (pm and pm.process) else False
            cm = ConfigManager()
            model_entry = cm.get_model_catalog().get("bge-reranker-v2-m3", {})
            model_path = model_entry.get("model_path", "")
            model_exists = os.path.exists(model_path) if model_path else False

            tb_str = traceback.format_exc()
            err_msg = (
                f"[RerankerProxyError] Fallback embedding adapter failed for target port {target_port}: {ex}\n"
                f"  Target URL: http://127.0.0.1:{target_port}/v1/rerank and /v1/embeddings\n"
                f"  Binary Mode: {binary_mode}\n"
                f"  Subprocess PID: {pid} (is_alive={is_alive})\n"
                f"  Model Path: {model_path} (exists={model_exists})\n"
                f"  Traceback:\n{tb_str}"
            )
            get_client_logger().log_error(err_msg)
            print(err_msg, file=sys.stderr)

    # Non-LLM 또는 Non-Streaming 요청: 기존 스트리밍 로직 유지
    async def stream_generator() -> AsyncGenerator[bytes, None]:
        """기존 Non-Queue 스트리밍 제너레이터 (Embedding, Reranker 등)."""
        first_chunk_received = False
        ttft_ms = 0.0
        start_time = time.perf_counter()
        captured_chunks = []

        async def _execute_stream():
            nonlocal first_chunk_received, ttft_ms
            try:
                async for chunk in r.aiter_raw():
                    if not first_chunk_received:
                        ttft_ms = (time.perf_counter() - start_time) * 1000.0
                        first_chunk_received = True
                    if await request.is_disconnected():
                        break
                    if is_llm_request:
                        captured_chunks.append(chunk)
                    yield chunk
            finally:
                await r.aclose()
                if is_llm_request:
                    try:
                        completion_text = ""
                        prompt_tokens = 0
                        completion_tokens = 0
                        if captured_chunks:
                            full_resp = b"".join(captured_chunks).decode("utf-8", errors="ignore")
                            if full_resp.strip().startswith("{"):
                                res_json = json.loads(full_resp)
                                choices = res_json.get("choices", [])
                                if choices:
                                    completion_text = choices[0].get("message", {}).get("content", "") or choices[0].get("text", "")
                                usage = res_json.get("usage", {})
                                prompt_tokens = usage.get("prompt_tokens", 0)
                                completion_tokens = usage.get("completion_tokens", 0)
                            else:
                                for line in full_resp.splitlines():
                                    line = line.strip()
                                    if line.startswith("data: ") and line != "data: [DONE]":
                                        try:
                                            c_json = json.loads(line[6:])
                                            choices = c_json.get("choices", [])
                                            if choices:
                                                delta = choices[0].get("delta", {})
                                                content = delta.get("content", "")
                                                if content:
                                                    completion_text += content
                                        except Exception:
                                            pass
                        thinking_text = None
                        if completion_text:
                            from src.core.think_tag_parser import parse_think_tags
                            clean_text, think_text = parse_think_tags(completion_text)
                            completion_text = clean_text
                            thinking_text = think_text

                        total_latency_s = time.perf_counter() - start_time
                        tps = round(completion_tokens / max(total_latency_s, 0.05), 1) if completion_tokens else 0.0
                        llama_manager.process_manager.record_tps_sample(tps)

                        auth_header = request.headers.get("authorization", "")
                        api_key = auth_header.replace("Bearer ", "").strip() if "Bearer " in auth_header else "anonymous"

                        from src.core.metrics_db import metrics_db
                        metrics_db.log_request(
                            api_key=api_key or "anonymous",
                            endpoint=request.url.path,
                            status_code=r.status_code,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            ttft_ms=round(ttft_ms, 2),
                            tps=tps,
                            is_error=(r.status_code >= 400),
                            prompt_text=prompt_text,
                            completion_text=completion_text,
                            thinking_text=thinking_text
                        )
                    except Exception:
                        pass

        if is_llm_request:
            req_model = model_id if "model_id" in locals() and model_id else "qwen3.5-2b"
            req_priority = priority if "priority" in locals() and priority else "high"
            async with priority_scheduler.schedule(model=req_model, priority=req_priority, task_name=clean_path):
                async for item in _execute_stream():
                    yield item
        else:
            async for item in _execute_stream():
                yield item

    # Filter out hop-by-hop & content length/encoding headers to prevent Uvicorn h11 LocalProtocolError
    excluded_headers = {"content-length", "transfer-encoding", "connection", "content-encoding"}
    response_headers = {
        k: v for k, v in r.headers.items()
        if k.lower() not in excluded_headers
    }

    return StreamingResponse(
        stream_generator(),
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

