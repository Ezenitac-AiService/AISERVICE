import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
from src.api.routes.inference_api import router as inference_router
from src.api.routes.health_api import router as health_router

@pytest.mark.asyncio
async def test_drain_mode_rejection():
    """Verify that during drain mode, inference requests are rejected with HTTP 503 Retry-After: 15."""
    app = FastAPI()
    app.state.drain_mode = True
    app.include_router(inference_router)
    app.include_router(health_router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Inference request rejected with 503 and Retry-After: 15
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "qwen3.5-9b", "messages": [{"role": "user", "content": "hi"}]}
        )
        assert resp.status_code == 503
        assert resp.headers.get("retry-after") == "15"
        assert "drain mode" in resp.json().get("detail", "").lower()

        # 2. Health readiness probe returns 503 with drain_mode=True
        health_resp = await client.get("/health/readiness")
        assert health_resp.status_code == 503
        data = health_resp.json()
        assert data.get("drain_mode") is True
        assert data.get("status") == "not_ready"
