"""
Unit tests for reverse_proxy response header filtering (069-fix-proxy-content-length-header).
Verifies that Content-Length, Transfer-Encoding, and Connection headers are stripped to prevent Uvicorn h11 LocalProtocolError.
"""

import pytest
from httpx import Headers
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fastapi.responses import StreamingResponse
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.routes.inference_api import router


@pytest.fixture
def app():
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.mark.asyncio
async def test_reverse_proxy_strips_content_length_and_transfer_encoding_headers(monkeypatch):
    """US1 & FR-001: Verify reverse_proxy removes content-length, transfer-encoding, and connection headers."""
    monkeypatch.delenv("MOCK_LLAMA_SERVER", raising=False)
    mock_upstream_headers = Headers({
        "content-type": "application/json",
        "content-length": "1285",
        "transfer-encoding": "chunked",
        "connection": "close",
        "x-custom-header": "test-value"
    })

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.headers = mock_upstream_headers

    async def mock_aiter_raw():
        yield b'{"choices": [{"message": {"content": "Hello world"}}]}'

    mock_response.aiter_raw = mock_aiter_raw

    mock_client = MagicMock()
    mock_client.build_request.return_value = MagicMock()
    mock_client.send = AsyncMock(return_value=mock_response)

    mock_request = MagicMock(spec=Request)
    mock_request.url.path = "/v1/chat/completions"
    mock_request.url.query = ""
    mock_request.method = "POST"
    mock_request.headers.raw = []
    mock_request.is_disconnected = AsyncMock(return_value=False)
    mock_request.body = AsyncMock(return_value=b'{"messages": [{"role": "user", "content": "hi"}]}')
    mock_request.app.state.http_client = mock_client

    with patch("src.api.routes.inference_api.check_llama_status", AsyncMock(return_value=True)):
        from src.api.routes.inference_api import reverse_proxy
        response = await reverse_proxy(mock_request, "chat/completions")

        assert isinstance(response, StreamingResponse)
        assert response.status_code == 200

        # Verify prohibited headers are stripped
        lowered_headers = {k.lower(): v for k, v in response.headers.items()}
        assert "content-length" not in lowered_headers, "Content-Length header MUST be stripped to prevent h11 protocol error"
        assert "transfer-encoding" not in lowered_headers, "Transfer-Encoding header MUST be stripped"
        assert "connection" not in lowered_headers, "Connection header MUST be stripped"
        assert lowered_headers.get("x-custom-header") == "test-value", "Custom headers should be preserved"
