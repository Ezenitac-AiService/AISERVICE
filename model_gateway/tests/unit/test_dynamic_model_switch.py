"""Unit tests for Dual-LLM routing and decommissioned model rejection (modernized from dynamic switch)."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import Request, Response
from httpx import Headers
from src.api.routes.inference_api import reverse_proxy


@pytest.mark.asyncio
async def test_reverse_proxy_rejects_decommissioned_model():
    """Verify reverse_proxy rejects decommissioned qwen3.5-2b with HTTP 404 model_not_found."""
    mock_request = MagicMock(spec=Request)
    mock_request.url.path = "/v1/chat/completions"
    mock_request.url.query = ""
    mock_request.method = "POST"
    mock_request.headers.raw = []
    mock_request.is_disconnected = AsyncMock(return_value=False)
    mock_request.body = AsyncMock(return_value=b'{"model": "qwen3.5-2b", "messages": [{"role": "user", "content": "hi"}]}')
    mock_request.app.state.drain_mode = False

    response = await reverse_proxy(mock_request, "chat/completions")
    assert response.status_code == 404
    data = json.loads(response.body)
    assert data["error"]["code"] == "model_not_found"
    assert "qwen3.5-2b" in data["error"]["message"]


@pytest.mark.asyncio
async def test_reverse_proxy_routes_4b_to_port_8088():
    """Verify reverse_proxy routes qwen3.5-4b to port 8088 without triggering unloads."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = Headers({"content-type": "application/json"})
    mock_response.content = b'{"choices": [{"message": {"content": "Hello"}}]}'
    mock_response.json.return_value = {"choices": [{"message": {"content": "Hello"}}], "usage": {}}

    mock_client = MagicMock()
    mock_client.build_request.return_value = MagicMock()
    mock_client.send = AsyncMock(return_value=mock_response)

    mock_request = MagicMock(spec=Request)
    mock_request.url.path = "/v1/chat/completions"
    mock_request.url.query = ""
    mock_request.method = "POST"
    mock_request.headers.raw = []
    mock_request.headers.get.return_value = ""
    mock_request.is_disconnected = AsyncMock(return_value=False)
    mock_request.body = AsyncMock(return_value=b'{"model": "qwen3.5-4b", "messages": [{"role": "user", "content": "hi"}]}')
    mock_request.app.state.http_client = mock_client
    mock_request.app.state.drain_mode = False

    response = await reverse_proxy(mock_request, "chat/completions")
    assert isinstance(response, Response)
    assert response.status_code == 200

    # Verify build_request was called with port 8088
    call_args = mock_client.build_request.call_args
    assert "8088" in call_args[0][1]
