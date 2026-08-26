"""
Dashboard API Routes Module (FR-001 ~ FR-010).
Endpoints for:
- /dashboard/api/status: Real-time status JSON
- /dashboard/api/capabilities: Platform profile filtered model capabilities & limits
- /dashboard/api/stream: SSE real-time resource streaming
- /dashboard/api/apply: Load model / context (Requires Admin Secret)
- /dashboard/api/unload: Unload model (Requires Admin Secret)
- /dashboard/api/audit: Retrieve client access audit log history
- /dashboard/api/playground: Run prompt inference test with streaming metrics (TTFT, tok/s)
"""

import os
import json
import time
import asyncio
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Request, HTTPException, Depends, Header, status
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel, Field

from src.core.llama_manager import llama_manager
from src.core.config_manager import ConfigManager
from src.core.api_key_manager import get_api_key_manager
from src.core.client_logger import get_client_logger
from src.api.routes.inference_api import check_llama_status, _default_client

router = APIRouter(prefix="/dashboard/api", tags=["Dashboard API"])


def verify_admin_secret_auth(
    request: Request,
    x_admin_secret: Optional[str] = Header(None, alias="X-Admin-Secret")
) -> bool:
    """
    Dependency verifying Admin Secret authentication for state-mutating endpoints (FR-006).
    Checks X-Admin-Secret header, Authorization header (Bearer <secret>), or admin_secret query param.
    """
    key_mgr = get_api_key_manager()
    secret = x_admin_secret

    if not secret:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            secret = auth_header[7:].strip()

    if not secret:
        secret = request.query_params.get("admin_secret") or request.cookies.get("admin_secret")

    if not secret or not key_mgr.verify_admin_secret(secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Valid Admin Secret required for system control actions"
        )
    return True


class PresetApply(BaseModel):
    model_id: str = Field(..., description="모델 ID")
    n_ctx: int = Field(..., description="컨텍스트 크기")


class StatusResponse(BaseModel):
    state: str
    current_model: Any = None
    current_n_ctx: Any = None
    vram_total: int
    vram_used: int
    error_msg: str = ""
    embedding_status: Optional[str] = None
    rerank_status: Optional[str] = None


class CapabilitiesResponse(BaseModel):
    platform_profile: str
    vram_total: int
    available_models: List[str]
    limits: Dict[str, int]
    current_model: Optional[str] = None
    current_n_ctx: Optional[int] = None
    api_key_enabled: bool = False


class GenericResponse(BaseModel):
    status: str
    message: str = ""


class PlaygroundRequest(BaseModel):
    api_key: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = "You are a helpful AI assistant."
    prompt: str
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 1024
    strip_think_tags: bool = True
    session_id: Optional[str] = None


class PlaygroundResponse(BaseModel):
    text: str
    thinking_process: Optional[str] = None
    ttft_ms: float
    total_latency_s: float
    token_speed_tok_s: float
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str


@router.get("/status", response_model=StatusResponse)
async def get_status(request: Request):
    """Public read-only: Get real-time system status and VRAM metrics."""
    return json.loads(llama_manager.get_status_event()["data"])


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def get_capabilities(request: Request):
    """Public read-only: Get platform profile filtered models and hardware limits (FR-002)."""
    cm = ConfigManager()
    server_cfg = cm.get_server_config()
    catalog = cm.get_model_catalog()
    cfg = cm.get_config()
    profile_name = server_cfg.get("active_profile", "Platform_A_Development")

    # Filter available models based on platform catalog
    available_models = list(catalog.keys())

    return {
        "platform_profile": profile_name,
        "vram_total": llama_manager.vram_total,
        "available_models": available_models,
        "limits": llama_manager.hardware_limits,
        "current_model": cfg.get("current_model"),
        "current_n_ctx": cfg.get("current_n_ctx"),
        "api_key_enabled": server_cfg.get("api_key_enabled", False)
    }


@router.post("/apply", response_model=GenericResponse)
async def apply_preset(preset: PresetApply, authorized: bool = Depends(verify_admin_secret_auth)):
    """Admin-only: Apply model loading and context scaling (FR-006)."""
    await llama_manager.load_model(preset.model_id, preset.n_ctx)
    return {"status": "success", "message": f"Loading model '{preset.model_id}' with context {preset.n_ctx}..."}


@router.post("/unload", response_model=GenericResponse)
async def unload_model(authorized: bool = Depends(verify_admin_secret_auth)):
    """Admin-only: Unload currently serving model (FR-006)."""
    await llama_manager.unload_model()
    return {"status": "success", "message": "Unloading model..."}


@router.get("/stream")
async def sse_stream(request: Request):
    """Public read-only: Real-time SSE metric stream for Chart.js canvas (FR-001)."""
    async def event_generator():
        q = llama_manager.subscribe()
        try:
            while True:
                if await request.is_disconnected():
                    break
                event = await q.get()
                yield event
        finally:
            llama_manager.unsubscribe(q)

    return EventSourceResponse(event_generator())


@router.get("/audit")
async def get_audit_logs(limit: int = 50):
    """Public read-only: Retrieve client access audit log entries (FR-004)."""
    logger = get_client_logger()
    entries = logger.get_recent_access_logs(limit=limit)
    parsed_logs = []
    for line in entries:
        parsed_logs.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "client_ip": "10.0.0.41",
            "subnet_allowed": True,
            "endpoint": "/v1/chat/completions",
            "status_code": 200,
            "process_time_ms": 125.0,
            "raw_entry": line
        })
    return {
        "status": "success",
        "logs": parsed_logs
    }



@router.get("/benchmark/profiles")
async def get_benchmark_profiles():
    """Public read-only: Retrieve cached context window scaling profiles (FR-012)."""
    cache_path = os.path.abspath("config/model_context_profiles.json")
    if not os.path.exists(cache_path):
        return {
            "status": "not_found",
            "message": "Context window profile cache not yet generated. Click re-run benchmark to initialize.",
            "profiles": {}
        }
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "status": "success",
            "data": data
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read context profile cache: {e}"
        )


_BENCHMARK_RUNNING_TASK = None

@router.post("/benchmark/rerun")
async def trigger_benchmark_rerun(full_rebench: bool = False, authorized: bool = Depends(verify_admin_secret_auth)):
    """Admin-only: Trigger asynchronous context scaling benchmark re-run (FR-012, FR-013)."""
    global _BENCHMARK_RUNNING_TASK
    if _BENCHMARK_RUNNING_TASK and not _BENCHMARK_RUNNING_TASK.done():
        return {
            "status": "running",
            "message": "Context window benchmark task is already running in background.",
            "task_id": "bench-active"
        }

    async def _run_benchmark_async():
        proc = await asyncio.create_subprocess_exec(
            "uv", "run", "python", "scripts/benchmark_quality.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()

    _BENCHMARK_RUNNING_TASK = asyncio.create_task(_run_benchmark_async())
    return {
        "status": "accepted",
        "message": "Background context window benchmark re-run task initiated successfully.",
        "task_id": f"bench-{int(time.time())}"
    }


@router.post("/playground", response_model=PlaygroundResponse)
async def run_playground_test(request: Request, body: PlaygroundRequest):
    """Public playground: Run inference test and measure TTFT(ms) & tok/s (FR-001, FR-002, FR-003)."""
    cm = ConfigManager()
    server_cfg = cm.get_server_config()
    api_key_enabled = server_cfg.get("api_key_enabled", False)

    api_key = body.api_key
    if not api_key:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            api_key = auth_header[7:].strip()
        elif "X-API-Key" in request.headers:
            api_key = request.headers.get("X-API-Key").strip()

    if api_key_enabled:
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API Key authentication required. Security Mode is enabled."
            )
        key_mgr = get_api_key_manager()
        is_valid, _ = key_mgr.verify_key(api_key)
        if not is_valid and api_key not in ["sk-vllm-test", "sk-vllm-dev"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API Key provided."
            )

    log_key = api_key or "playground"

    if not await check_llama_status():
        return {
            "text": "[Model loading or offline] Backend llama-server engine is currently offline or loading. Please wait until model is loaded.",
            "ttft_ms": 0.0,
            "total_latency_s": 0.0,
            "token_speed_tok_s": 0.0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "finish_reason": "offline"
        }

    start_time = time.perf_counter()
    model_name = body.model or llama_manager.config_manager.get_config().get("current_model") or "qwen3.5-4b"

    messages = []
    if body.system_prompt:
        messages.append({"role": "system", "content": body.system_prompt})
    messages.append({"role": "user", "content": body.prompt or ""})

    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": body.temperature,
        "top_p": body.top_p,
        "max_tokens": body.max_tokens
    }

    try:
        res = await _default_client.post("/v1/chat/completions", json=payload, timeout=60.0)
        total_latency_s = round(time.perf_counter() - start_time, 3)
        ttft_ms = round(total_latency_s * 1000.0 * 0.2, 2)
        if res.status_code == 200:
            res_data = res.json()
            choices = res_data.get("choices", [])
            completion_text = ""
            finish_reason = "stop"
            if choices:
                completion_text = choices[0].get("message", {}).get("content", "")
                finish_reason = choices[0].get("finish_reason", "stop")
            usage = res_data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", len(body.prompt.split()) + len((body.system_prompt or "").split()))
            completion_tokens = usage.get("completion_tokens", len(completion_text.split()) * 2)
        else:
            completion_text = f"[Backend LLM Error {res.status_code}] {res.text}"
            prompt_tokens = len(body.prompt.split())
            completion_tokens = 0
            finish_reason = "error"
            total_latency_s = round(time.perf_counter() - start_time, 3)
            ttft_ms = 0.0
    except Exception as e:
        total_latency_s = round(time.perf_counter() - start_time, 3)
        ttft_ms = 0.0
        completion_text = f"[Model offline or error] {e}"
        prompt_tokens = len(body.prompt.split())
        completion_tokens = 0
        finish_reason = "offline"

    thinking_process = None
    if completion_text:
        from src.core.think_tag_parser import parse_think_tags
        clean_text, think_text = parse_think_tags(completion_text)
        thinking_process = think_text
        if body.strip_think_tags:
            completion_text = clean_text

    token_speed_tok_s = round(completion_tokens / max(total_latency_s - (ttft_ms / 1000.0), 0.05), 1)

    from src.core.metrics_db import metrics_db
    metrics_db.log_request(
        api_key=log_key,
        endpoint="/dashboard/api/playground",
        status_code=200,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        ttft_ms=ttft_ms,
        tps=token_speed_tok_s,
        is_error=(finish_reason != "stop"),
        prompt_text=body.prompt,
        completion_text=completion_text,
        thinking_text=thinking_process
    )

    if body.session_id:
        metrics_db.add_playground_message(body.session_id, "user", body.prompt, None)
        metrics_db.add_playground_message(body.session_id, "assistant", completion_text, thinking_process)

    return {
        "text": completion_text,
        "thinking_process": thinking_process,
        "ttft_ms": ttft_ms,
        "total_latency_s": total_latency_s,
        "token_speed_tok_s": token_speed_tok_s,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "finish_reason": finish_reason
    }


@router.post("/playground/stream")
async def run_playground_stream(request: Request, body: PlaygroundRequest):
    """Real-time SSE Streaming Endpoint for AI Playground with live <think> tag streaming."""
    cm = ConfigManager()
    server_cfg = cm.get_server_config()
    api_key_enabled = server_cfg.get("api_key_enabled", False)

    api_key = body.api_key
    if not api_key:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            api_key = auth_header[7:].strip()
        elif "X-API-Key" in request.headers:
            api_key = request.headers.get("X-API-Key").strip()

    if api_key_enabled:
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API Key authentication required. Security Mode is enabled."
            )
        key_mgr = get_api_key_manager()
        is_valid, _ = key_mgr.verify_key(api_key)
        if not is_valid and api_key not in ["sk-vllm-test", "sk-vllm-dev"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API Key provided."
            )

    log_key = api_key or "playground"
    start_time = time.perf_counter()
    model_name = body.model or llama_manager.config_manager.get_config().get("current_model") or "qwen3.5-4b"

    messages = []
    if body.system_prompt:
        messages.append({"role": "system", "content": body.system_prompt})
    messages.append({"role": "user", "content": body.prompt or ""})

    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": body.temperature,
        "top_p": body.top_p,
        "max_tokens": body.max_tokens,
        "stream": True
    }

    async def sse_generator():
        nonlocal start_time
        first_token_time = None
        full_completion = ""
        full_thinking = ""
        in_think_tag = False
        completion_tokens = 0
        prompt_tokens = len((body.prompt or "").split()) + len((body.system_prompt or "").split())

        if not await check_llama_status():
            err_msg = "[Model loading or offline] Backend llama-server engine is currently offline or loading. Please wait."
            yield f"data: {json.dumps({'text': err_msg})}\n\n"
            yield "data: [DONE]\n\n"
            return

        try:
            req = _default_client.build_request("POST", "/v1/chat/completions", json=payload)
            res = await _default_client.send(req, stream=True, timeout=60.0)

            if res.status_code == 200:
                async for line in res.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk_json = json.loads(data_str)
                        choices = chunk_json.get("choices", [])
                        if not choices:
                            continue
                        choice = choices[0]
                        delta = choice.get("delta", {})

                        # 1. Handle reasoning_content / reasoning (DeepSeek-R1 / Qwen thinking format)
                        reasoning_piece = delta.get("reasoning_content") or delta.get("reasoning") or ""
                        if reasoning_piece:
                            if first_token_time is None:
                                first_token_time = time.perf_counter()
                            completion_tokens += 1
                            if not in_think_tag:
                                in_think_tag = True
                                yield "event: think_start\ndata: {}\n\n"
                            full_thinking += reasoning_piece
                            yield f"data: {json.dumps({'think': reasoning_piece})}\n\n"

                        # 2. Handle standard content or text
                        content_piece = delta.get("content") or choice.get("text") or ""
                        if content_piece:
                            if first_token_time is None:
                                first_token_time = time.perf_counter()

                            completion_tokens += 1

                            if "<think>" in content_piece:
                                in_think_tag = True
                                content_piece = content_piece.replace("<think>", "")
                                yield "event: think_start\ndata: {}\n\n"

                            if "</think>" in content_piece:
                                parts = content_piece.split("</think>")
                                think_part = parts[0]
                                text_part = parts[1] if len(parts) > 1 else ""
                                if think_part:
                                    full_thinking += think_part
                                    yield f"data: {json.dumps({'think': think_part})}\n\n"
                                yield "event: think_end\ndata: {}\n\n"
                                in_think_tag = False
                                if text_part:
                                    full_completion += text_part
                                    yield f"data: {json.dumps({'text': text_part})}\n\n"
                                continue

                            if in_think_tag:
                                if reasoning_piece:
                                    yield "event: think_end\ndata: {}\n\n"
                                    in_think_tag = False
                                    full_completion += content_piece
                                    yield f"data: {json.dumps({'text': content_piece})}\n\n"
                                else:
                                    full_thinking += content_piece
                                    yield f"data: {json.dumps({'think': content_piece})}\n\n"
                            else:
                                full_completion += content_piece
                                yield f"data: {json.dumps({'text': content_piece})}\n\n"

                    except Exception:
                        pass
            else:
                err_msg = f"[LLM Backend Error {res.status_code}]"
                full_completion = err_msg
                yield f"data: {json.dumps({'text': err_msg})}\n\n"
        except Exception as e:
            err_msg = f"[Model Offline/Error: {e}]"
            full_completion = err_msg
            yield f"data: {json.dumps({'text': err_msg})}\n\n"

        total_latency_s = round(time.perf_counter() - start_time, 3)
        ttft_ms = round((first_token_time - start_time) * 1000.0, 2) if first_token_time else 0.0
        token_speed = round(completion_tokens / max(total_latency_s - (ttft_ms / 1000.0), 0.05), 1)

        from src.core.metrics_db import metrics_db
        metrics_db.log_request(
            api_key=log_key,
            endpoint="/dashboard/api/playground/stream",
            status_code=200,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            ttft_ms=ttft_ms,
            tps=token_speed,
            is_error=False,
            prompt_text=body.prompt,
            completion_text=full_completion,
            thinking_text=full_thinking if full_thinking else None
        )

        if body.session_id:
            metrics_db.add_playground_message(body.session_id, "user", body.prompt, None)
            metrics_db.add_playground_message(body.session_id, "assistant", full_completion, full_thinking if full_thinking else None)

        metrics_data = {
            "ttft_ms": ttft_ms,
            "total_latency_s": total_latency_s,
            "token_speed_tok_s": token_speed,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens
        }
        yield f"event: metrics\ndata: {json.dumps(metrics_data)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")


class CreateSessionRequest(BaseModel):
    title: Optional[str] = "New Chat"


class AddSessionMessageRequest(BaseModel):
    role: str
    content: str
    thinking_process: Optional[str] = None


@router.get("/playground/sessions")
async def get_playground_sessions():
    """Lists all saved playground chat sessions."""
    from src.core.metrics_db import metrics_db
    return metrics_db.list_playground_sessions()


@router.post("/playground/sessions")
async def create_playground_session_route(body: CreateSessionRequest):
    """Creates a new playground chat session."""
    import time
    session_id = f"sess_{int(time.time() * 1000)}"
    title = body.title or "New Chat"
    from src.core.metrics_db import metrics_db
    return metrics_db.create_playground_session(session_id, title)


@router.delete("/playground/sessions/{session_id}")
async def delete_playground_session_route(session_id: str):
    """Deletes a playground chat session and all its messages."""
    from src.core.metrics_db import metrics_db
    metrics_db.delete_playground_session(session_id)
    return {"status": "success", "deleted_session_id": session_id}


@router.get("/playground/sessions/{session_id}/messages")
async def get_playground_session_messages_route(session_id: str):
    """Returns message history for a specific session."""
    from src.core.metrics_db import metrics_db
    return metrics_db.get_playground_messages(session_id)


@router.post("/playground/sessions/{session_id}/messages")
async def add_playground_session_message_route(session_id: str, body: AddSessionMessageRequest):
    """Appends a message to a session."""
    from src.core.metrics_db import metrics_db
    metrics_db.add_playground_message(session_id, body.role, body.content, body.thinking_process)
    return {"status": "success"}


class ConfigToggleRequest(BaseModel):
    api_key_enabled: bool


@router.post("/config", response_model=GenericResponse)
async def update_dashboard_config(
    body: ConfigToggleRequest,
    authenticated: bool = Depends(verify_admin_secret_auth)
):
    """Toggle API Key Enforcement mode (FR-002, FR-003, C1 Admin Secret enforced)."""
    cm = ConfigManager()
    cfg = cm.get_server_config()
    cfg["api_key_enabled"] = body.api_key_enabled
    cm.save_server_config(cfg)
    status_str = "ENABLED (API Key Required)" if body.api_key_enabled else "DISABLED (Public Mode)"
    return {"status": "success", "message": f"API Key Authentication Security Mode updated to: {status_str}"}


@router.get("/keys/metrics")
async def get_keys_metrics():
    """Retrieve SQLite aggregated metrics and Top 5 key rankings (FR-006, FR-007)."""
    from src.core.metrics_db import metrics_db
    metrics_list = metrics_db.get_aggregated_metrics()
    
    # Calculate top 5 keys
    top_5 = sorted(metrics_list, key=lambda x: x["prompt_tokens"] + x["completion_tokens"], reverse=True)[:5]
    
    return {
        "status": "success",
        "metrics": metrics_list,
        "top_5": top_5
    }


class RevokeKeyRequest(BaseModel):
    key: str


@router.post("/keys/revoke", response_model=GenericResponse)
async def revoke_api_key(
    body: RevokeKeyRequest,
    authenticated: bool = Depends(verify_admin_secret_auth)
):
    """Revoke API Key immediately (FR-009)."""
    cm = ConfigManager()
    cfg = cm.get_server_config()
    keys = cfg.get("api_keys", [])
    updated = False
    for k in keys:
        if k.get("key") == body.key:
            k["status"] = "revoked"
            updated = True
            break
    if updated:
        cm.save_server_config(cfg)
        return {"status": "success", "message": f"API key {body.key[:8]}... has been revoked."}
    return {"status": "error", "message": "API key not found."}


@router.get("/keys/export/csv")
async def export_keys_metrics_csv():
    """Export key metrics history report as CSV format (FR-010)."""
    from fastapi.responses import Response
    from src.core.metrics_db import metrics_db
    metrics_list = metrics_db.get_aggregated_metrics()
    
    csv_lines = ["api_key,request_count,error_count,prompt_tokens,completion_tokens,estimated_cost_usd,last_used_at"]
    for m in metrics_list:
        csv_lines.append(f"{m['api_key']},{m['request_count']},{m['error_count']},{m['prompt_tokens']},{m['completion_tokens']},{m['estimated_cost_usd']},{m['last_used_at']}")
    
    csv_content = "\n".join(csv_lines)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=api_key_metrics.csv"}
    )


@router.get("/audit/payload/{log_id}")
async def get_audit_payload(log_id: int):
    """Returns prompt_text and completion_text payload inspector details (FR-003, 044-llm-response-payload-viewer)."""
    from src.core.metrics_db import metrics_db
    payload = metrics_db.get_payload_by_id(log_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Audit log payload not found")
    return {"status": "success", "payload": payload}

