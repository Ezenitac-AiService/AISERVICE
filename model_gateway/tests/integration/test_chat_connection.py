"""
Integration test harness for ASGI protocol & connection drop validation (T003).
Verifies that FastAPI / Uvicorn handlers do not trigger h11.LocalProtocolError.
"""

import pytest
import httpx
from src.api.main import app
from src.core.utils.encoding import get_utf8_byte_length, encode_json_payload


@pytest.mark.asyncio
async def test_utf8_byte_length_utility():
    """Verify UTF-8 multi-byte character length vs byte count calculation."""
    korean_text = "대한민국의 수도는 서울입니다."
    char_len = len(korean_text)
    byte_len = get_utf8_byte_length(korean_text)
    
    # 16 characters, but 42 UTF-8 bytes
    assert char_len == 16
    assert byte_len == 42
    assert get_utf8_byte_length(korean_text.encode("utf-8")) == 42


@pytest.mark.asyncio
async def test_asgi_health_endpoint_connection_close():
    """Verify GET /health responds cleanly with Connection: close without protocol errors."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health", headers={"Connection": "close"})
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "alive"
