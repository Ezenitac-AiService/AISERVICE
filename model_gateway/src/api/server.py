"""
FastAPI Server Entrypoint and Factory Module (FR-001, FR-002, FR-005, FR-008, FR-068, FR-074).
Configures routes, SubnetFilterMiddleware, APIKeyAuthMiddleware, RequestBodyLimitMiddleware,
outermost CORSMiddleware, static assets with symlink protection, and lifespan active drain.
"""

import os
import asyncio
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from src.core.llama_manager import llama_manager
from src.core.config_manager import ConfigManager
from src.core.auxiliary_manager import auxiliary_manager
from src.core.queue_manager import gpu_queue

from src.api.routes.inference_api import router as inference_router
from src.api.routes.dashboard_api import router as dashboard_router
from src.api.routes.admin_api import router as admin_router
from src.api.routes.health_api import router as health_router

from src.api.middleware.subnet_filter import SubnetFilterMiddleware
from src.api.middleware.client_access_logger import ClientAccessLogMiddleware
from src.api.middleware.api_key_auth import APIKeyAuthMiddleware
from src.api.middleware.body_limit import RequestBodyLimitMiddleware
from src.core.middleware.protocol_guard import ProtocolGuardMiddleware

DRAIN_TIMEOUT_SECONDS = float(os.getenv("DRAIN_TIMEOUT_SECONDS", "15.0"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager with startup initialization and active drain on shutdown."""
    cm = ConfigManager()
    server_cfg = cm.get_server_config()
    backend_port = server_cfg.get("backend_port", 8089) if server_cfg else 8089

    # Initialize singleton httpx.AsyncClient with explicit timeouts & limits (FR-052 & T019)
    limits = httpx.Limits(max_keepalive_connections=20, max_connections=100, keepalive_expiry=5.0)
    timeout = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)
    app.state.http_client = httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{backend_port}",
        limits=limits,
        timeout=timeout
    )
    app.state.drain_mode = False

    async def reset_http_client():
        """T019: Invalidate and rebuild connection pool upon process restart to purge dead sockets."""
        try:
            if hasattr(app.state, "http_client") and app.state.http_client:
                await app.state.http_client.aclose()
        except Exception:
            pass
        fresh_limits = httpx.Limits(max_keepalive_connections=20, max_connections=100, keepalive_expiry=5.0)
        app.state.http_client = httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{backend_port}",
            limits=fresh_limits,
            timeout=timeout
        )

    app.state.reset_http_client = reset_http_client

    # Auto-load default resident Dual-LLM models and auxiliary (Embedding/Reranker) instances
    async def safe_startup_llm():
        try:
            await asyncio.sleep(1.0)
            await llama_manager.ensure_default_model_resident()
        except Exception as e:
            print(f"[Lifespan Error - LLM Startup]: {e}")
            import traceback
            traceback.print_exc()

    async def safe_startup_aux():
        try:
            await asyncio.sleep(6.0)
            await auxiliary_manager.start_auto_startup_and_recovery()
        except Exception as e:
            print(f"[Lifespan Error - Aux Startup]: {e}")
            import traceback
            traceback.print_exc()

    asyncio.create_task(safe_startup_llm())
    asyncio.create_task(safe_startup_aux())
    asyncio.create_task(llama_manager.start_health_monitor(interval_seconds=3.0))

    yield

    # T038 / FR-060 / FR-074: Graceful Lifespan Active Drain Mode
    print(f"[Shutdown] Entering drain mode ({DRAIN_TIMEOUT_SECONDS}s timeout)...")
    app.state.drain_mode = True

    drain_deadline = asyncio.get_event_loop().time() + DRAIN_TIMEOUT_SECONDS
    while asyncio.get_event_loop().time() < drain_deadline:
        active_count = gpu_queue.active_count if hasattr(gpu_queue, "active_count") else 0
        if active_count == 0:
            print("[Shutdown] All active GPU slots drained cleanly.")
            break
        await asyncio.sleep(0.5)

    await app.state.http_client.aclose()
    await llama_manager.unload_model()
    await auxiliary_manager.shutdown()
    print("[Shutdown] Gateway shutdown complete.")


def create_app() -> FastAPI:
    """Create and configure FastAPI application instance with subnets middleware, routers, and CORS."""
    app = FastAPI(
        title="Model Gateway GPU Serving API",
        description="Model Gateway Dual-LLM RTX 3060 12GB GPU 서빙 API",
        version="2.1.0",
        lifespan=lifespan
    )

    # 1. Mount application routers (routes_v1 decommissioned to eliminate fake mocks)
    app.include_router(admin_router)
    app.include_router(inference_router)
    app.include_router(dashboard_router)
    app.include_router(health_router)

    # 2. Mount static dashboard files with symlink traversal prevention (CWE-22)
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.exists(static_dir):
        app.mount("/dashboard", StaticFiles(directory=static_dir, html=True, follow_symlink=False), name="dashboard")

    @app.get("/")
    async def root():
        """Redirect root path to dashboard."""
        return RedirectResponse(url="/dashboard/")

    # 3. Add middlewares in inside-out execution order:
    # Innermost: ProtocolGuardMiddleware (handles raw protocol frames)
    app.add_middleware(ProtocolGuardMiddleware)

    # Subnet filtering
    cm = ConfigManager()
    allowed_subnets = cm.get_allowed_subnets()
    app.add_middleware(SubnetFilterMiddleware, allowed_subnets=allowed_subnets)

    # Access logger (attaches X-Request-ID, records audit log)
    app.add_middleware(ClientAccessLogMiddleware)

    # API key authentication & rate limiting
    app.add_middleware(APIKeyAuthMiddleware)

    # Pure ASGI Request Body Size Limit Middleware (2MB) (HTTP 413)
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=2 * 1024 * 1024)

    # Outermost: CORSMiddleware (last added executes first, guaranteeing CORS headers on 4xx/5xx errors)
    cors_origins = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:8081",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:8081",
    ]
    env_origins = os.getenv("CORS_ALLOWED_ORIGINS")
    if env_origins:
        for o in env_origins.split(","):
            o = o.strip()
            if o and o not in cors_origins:
                cors_origins.append(o)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    import traceback
    cm = ConfigManager()
    server_cfg = cm.get_server_config()
    port = int(server_cfg.get("port", 8081) if server_cfg else 8081)
    host = str(server_cfg.get("host", "0.0.0.0") if server_cfg else "0.0.0.0")
    try:
        uvicorn.run("src.api.server:app", host=host, port=port, reload=False)
    except Exception as e:
        print(f"[Fatal Server Error]: {e}")
        traceback.print_exc()
