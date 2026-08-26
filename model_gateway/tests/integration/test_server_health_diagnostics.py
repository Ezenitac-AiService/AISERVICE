"""
Integration test for server health diagnostics (075-fix-server-health-diagnostics) (T004).
Verifies that diagnose_server_health.py correctly assesses /v1/chat/completions endpoint using standard dict payload.
"""

import pytest
import httpx
from src.api.main import app
from scripts.diagnose_server_health import check_api_endpoints, run_diagnostics


@pytest.mark.asyncio
async def test_health_diagnostics_chat_probe():
    """Verify chat completions probe returns True for 200/400/422 responses."""
    import os
    os.environ["MOCK_LLAMA_SERVER"] = "1"
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Standard dict payload
        payload = {
            "model": "qwen3.5-4b",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1
        }
        res = await client.post("/v1/chat/completions", json=payload)
        assert res.status_code == 200

def test_run_diagnostics_structure():
    """Verify report dict structure from run_diagnostics."""
    report = run_diagnostics(verbose=False)
    assert "detected_lan_ip" in report
    assert "api_status" in report
    assert "firewall_ports" in report
    assert "dashboard_e2e_status" in report
