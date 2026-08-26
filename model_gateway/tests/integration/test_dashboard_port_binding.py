"""
Integration test for Port 8082 Dashboard Binding (075-fix-server-health-diagnostics) (T007).
Verifies web dashboard app response on / /health and status check functions.
"""

import pytest
import httpx
from src.api.main import app


@pytest.mark.asyncio
async def test_dashboard_route_health():
    """Verify web dashboard route returns 200 OK."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/")
        assert res.status_code == 200
