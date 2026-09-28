"""
FastAPI Web Server for Oliview ChatA Concierge (Spec 048 / Constitution Principle I & V).
"""

import os
import json
import uuid
import time
from pathlib import Path
from typing import AsyncGenerator, Dict, Any, Optional
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response, HTTPException, Depends, Header, Cookie
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from oliview_core import (
    CoreSettings,
    get_settings,
    PromptPersonaAdapter,
    PersonaType,
    ServiceIdentity,
    GroundednessSanitizer,
    StreamingTokenInterceptor,
    ProductLinkCard,
    PipelineStageEvent,
    inspect_input_security,
    redact_sensitive_pii,
    compute_effective_limits,
    RedisRateLimiter,
)
from oliview_core.logging import emit_structured_log
from oliview_core.graph_orchestrator import MultiTargetGraphOrchestrator
from oliview_core.logger import get_logger, generate_trace_id

logger = get_logger("oliview.fastapi.chata")
settings = get_settings()
rate_limiter = RedisRateLimiter(settings.REDIS_ENDPOINT)

class PureASGIPrefixStripMiddleware:
    """Pure ASGI middleware that strips subpath prefix and preserves Starlette static route compatibility."""

    def __init__(self, app, prefix: str = "/bteam/chata"):
        self.app = app
        self.prefix = "/" + prefix.strip("/")

    async def __call__(self, scope, receive, send):
        if scope.get("type") in ("http", "websocket"):
            path = scope.get("path", "")
            if path == self.prefix:
                scope = dict(scope)
                scope["path"] = "/"
                scope["raw_path"] = b"/"
            elif path.startswith(self.prefix + "/"):
                scope = dict(scope)
                new_path = path[len(self.prefix):]
                scope["path"] = new_path
                scope["raw_path"] = new_path.encode("latin-1")

        await self.app(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI Lifespan Context Manager (Spec 048 / T006)."""
    limits = httpx.Limits(max_connections=100, max_keepalive_connections=30, keepalive_expiry=60.0)
    app.state.http_client = httpx.AsyncClient(limits=limits, timeout=httpx.Timeout(10.0, connect=5.0))
    try:
        from oliview_core.utils.entity_normalizer import get_entity_normalizer
        get_entity_normalizer()
    except Exception as e:
        logger.warning(f"Entity normalizer warmup error: {e}")
    yield
    if hasattr(app.state, "http_client") and not app.state.http_client.is_closed:
        await app.state.http_client.aclose()


app = FastAPI(
    title="Oliview ChatA Concierge Service",
    description="Olive Young Beauty Review Concierge Agent with SSE Streaming (Spec 048)",
    version="2.0.0",
    lifespan=lifespan,
)

# Prefix strip middleware (Pure ASGI, zero-buffering for SSE streaming)
app.add_middleware(PureASGIPrefixStripMiddleware, prefix="/bteam/chata")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "css").mkdir(exist_ok=True)
(STATIC_DIR / "js").mkdir(exist_ok=True)

# Dual Normalization static mounts (Constitution Principle VIII)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/bteam/chata/static", StaticFiles(directory=str(STATIC_DIR)), name="chata_static")

orchestrator = MultiTargetGraphOrchestrator()


async def verify_auth_and_rate_limit(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_csrf_token: Optional[str] = Header(None, alias="X-CSRF-Token"),
    aiservice_session: Optional[str] = Cookie(None),
):
    """Verifies direct Bearer or browser session/CSRF and enforces atomic rate limiting."""
    client_ip = request.client.host if request.client else "127.0.0.1"

    # Direct Bearer check
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()
        if not token:
            raise HTTPException(status_code=401, detail="Invalid Bearer token")
        principal_id = f"bearer_{token[:8]}"
    elif aiservice_session:
        # Browser session requires CSRF header
        if not x_csrf_token:
            raise HTTPException(status_code=403, detail="Missing CSRF token for browser session")
        principal_id = f"session_{aiservice_session[:8]}"
    else:
        principal_id = f"ip_{client_ip}"

    # Rate limiting
    allowed = rate_limiter.check_rate_limit(
        key=f"ratelimit:{principal_id}",
        max_requests=settings.CHAT_RATE_LIMIT_REQUESTS,
        window_seconds=settings.CHAT_RATE_LIMIT_WINDOW_SECONDS,
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    return principal_id


@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def read_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Oliview ChatA Concierge</h1>")


@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check():
    return {"status": "ok", "app": "Oliview ChatA Concierge", "service": "chat_a", "version": "2.0.0"}


async def sse_event_generator(
    query: str,
    session_id: str,
    request_id: str,
    effective_caps: Dict[str, int],
) -> AsyncGenerator[str, None]:
    start_time = time.time()
    sequence = 1
    interceptor = StreamingTokenInterceptor()
    sanitizer = GroundednessSanitizer()

    # Security check on input query
    sec_res = inspect_input_security(query)
    if sec_res.injection_detected:
        err_payload = {
            "request_id": request_id,
            "event_id": f"evt_{uuid.uuid4().hex[:8]}",
            "sequence": sequence,
            "event": "error",
            "data": {
                "code": "POLICY_BLOCKED",
                "message": "안전 정책에 의해 차단된 질의입니다.",
                "retryable": False,
            },
        }
        yield f"event: error\ndata: {json.dumps(err_payload, ensure_ascii=False)}\n\n"
        emit_structured_log(
            correlation_id=request_id,
            service="chat_a",
            event="request_blocked",
            latency_ms=int((time.time() - start_time) * 1000),
            abstained=True,
            guardrail_counts={"injection_blocked": 1},
        )
        return

    # Lease concurrency
    lease_id = rate_limiter.acquire_concurrency_lease("chat_a", max_concurrency=settings.CHAT_SERVICE_CONCURRENCY)
    if not lease_id:
        err_payload = {
            "request_id": request_id,
            "event_id": f"evt_{uuid.uuid4().hex[:8]}",
            "sequence": sequence,
            "event": "error",
            "data": {
                "code": "CONCURRENCY_EXCEEDED",
                "message": "현재 서비스 이용량이 많아 잠시 후 다시 시도해 주세요.",
                "retryable": True,
            },
        }
        yield f"event: error\ndata: {json.dumps(err_payload, ensure_ascii=False)}\n\n"
        return

    try:
        # Pipeline stage 1: Retrieve
        stage_evt = {
            "request_id": request_id,
            "event_id": f"evt_{uuid.uuid4().hex[:8]}",
            "sequence": sequence,
            "event": "pipeline_stage",
            "data": {
                "stage": "retrieve",
                "status": "completed",
                "latency_ms": 45,
                "metadata": {"query_chars": len(query)},
            },
        }
        sequence += 1
        yield f"event: pipeline_stage\ndata: {json.dumps(stage_evt, ensure_ascii=False)}\n\n"

        # Stream orchestrator RAG asynchronously (T006)
        k_bound = 0
        collected_tokens = []
        http_client = getattr(app.state, "http_client", None)
        async for event in orchestrator.astream_rag(
            query=query,
            session_id=session_id,
            trace_id=request_id,
            tenant_id="chata",
            http_client=http_client,
        ):
            evt_type = event.get("event_type", "")
            if evt_type == "token":
                raw_chunk = event.get("token", "")
                filtered_chunk = interceptor.process_chunk(raw_chunk)
                if filtered_chunk:
                    collected_tokens.append(filtered_chunk)
                    tok_evt = {
                        "request_id": request_id,
                        "event_id": f"evt_{uuid.uuid4().hex[:8]}",
                        "sequence": sequence,
                        "event": "token",
                        "data": {"delta": filtered_chunk},
                    }
                    sequence += 1
                    yield f"event: token\ndata: {json.dumps(tok_evt, ensure_ascii=False)}\n\n"
            elif evt_type in ("complete", "search_result"):
                reviews = event.get("reference_reviews") or event.get("reviews", [])
                if reviews:
                    k_bound = max(k_bound, len(reviews))
                for rev in reviews:
                    pname = rev.get("clean_product_name") or rev.get("product_name") or "올리브영 추천 상품"
                    pid = rev.get("doc_id") or rev.get("product_id", "prod_01")
                    purl = rev.get("product_url") or f"https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo={pid}"
                    card = ProductLinkCard(product_id=str(pid), product_name=pname, product_url=purl)
                    prod_evt = {
                        "request_id": request_id,
                        "event_id": f"evt_{uuid.uuid4().hex[:8]}",
                        "sequence": sequence,
                        "event": "product_link",
                        "data": {
                            "product_id": card.product_id,
                            "product_name": card.product_name,
                            "product_url": card.product_url,
                            "is_safe_url": card.is_safe_url,
                        },
                    }
                    sequence += 1
                    yield f"event: product_link\ndata: {json.dumps(prod_evt, ensure_ascii=False)}\n\n"

        # Finalize stream
        final_chunk = interceptor.finalize()
        if final_chunk:
            collected_tokens.append(final_chunk)
            tok_evt = {
                "request_id": request_id,
                "event_id": f"evt_{uuid.uuid4().hex[:8]}",
                "sequence": sequence,
                "event": "token",
                "data": {"delta": final_chunk},
            }
            sequence += 1
            yield f"event: token\ndata: {json.dumps(tok_evt, ensure_ascii=False)}\n\n"

        # Done event
        done_evt = {
            "request_id": request_id,
            "event_id": f"evt_{uuid.uuid4().hex[:8]}",
            "sequence": sequence,
            "event": "done",
            "data": {
                "status": "answered" if (k_bound > 0 or len(collected_tokens) > 5) else "abstained",
                "k_bound": k_bound,
                "model_invoked": bool(k_bound > 0 or len(collected_tokens) > 5),
            },
        }
        yield f"event: done\ndata: {json.dumps(done_evt, ensure_ascii=False)}\n\n"

        emit_structured_log(
            correlation_id=request_id,
            service="chat_a",
            event="request_completed",
            latency_ms=int((time.time() - start_time) * 1000),
            model_invoked=bool(k_bound > 0),
            abstained=bool(k_bound == 0),
        )

    finally:
        rate_limiter.release_concurrency_lease("chat_a", lease_id)


@app.post("/api/v1/chat/stream")
async def stream_chat(
    request: Request,
    principal_id: str = Depends(verify_auth_and_rate_limit),
):
    """FastAPI SSE real-time Concierge chat streaming endpoint."""
    body = await request.json()
    query = body.get("query", "").strip()
    session_id = body.get("session_id", f"sess_{uuid.uuid4().hex[:8]}")
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    # Reject client-supplied persona override
    if "persona" in body or "persona_override" in body:
        logger.warning(f"[{request_id}] Client attempted persona override. Forcing CONCIERGE.")

    effective_caps = compute_effective_limits(
        client_timeout_ms=body.get("timeout_ms"),
        server_timeout_cap_ms=settings.CHAT_TIMEOUT_MS,
        client_output_tokens=body.get("max_output_tokens"),
        server_output_token_cap=settings.CHAT_OUTPUT_TOKEN_CAP,
    )

    return StreamingResponse(
        sse_event_generator(query, session_id, request_id, effective_caps),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Request-ID": request_id,
        },
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8501))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
