import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
from src.api.routes.health_api import router as health_router

@pytest.mark.asyncio
async def test_prometheus_metrics_endpoint():
    """Verify Prometheus /metrics returns active context windows and Dual-LLM gauges."""
    app = FastAPI()
    app.include_router(health_router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/metrics")
        assert resp.status_code == 200
        text = resp.text

        # Verify Dual-LLM gateway up metrics
        assert 'llm_gateway_up{model="qwen3.5-9b",port="8089"}' in text
        assert 'llm_gateway_up{model="qwen3.5-4b",port="8088"}' in text

        # Verify VRAM gauges
        assert "gpu_vram_used_megabytes" in text
        assert "gpu_vram_total_megabytes" in text

        # Verify active context window sizes (32K for 9B, 8K for 4B)
        assert 'llm_context_window_tokens{model="qwen3.5-9b",port="8089"} 32768' in text
        assert 'llm_context_window_tokens{model="qwen3.5-4b",port="8088"} 8192' in text
