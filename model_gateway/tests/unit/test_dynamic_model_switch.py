"""Unit tests for dynamic model switching (FR-001, FR-002, FR-004, SC-001).

Feature: 116-fix-model-switching
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from httpx import Headers
from src.core.process_manager import ProcessStatusEnum, ProcessState
from src.api.routes.inference_api import router, reverse_proxy


@pytest.fixture
def app():
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.mark.asyncio
async def test_reverse_proxy_triggers_hot_swap_when_model_changes(monkeypatch):
    """FR-001 & SC-001: Verify reverse_proxy triggers load_model_with_download when requested model differs from resident model."""
    monkeypatch.delenv("MOCK_LLAMA_SERVER", raising=False)

    mock_upstream_headers = Headers({"content-type": "application/json"})
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.headers = mock_upstream_headers

    async def mock_aiter_raw():
        yield b'{"choices": [{"message": {"content": "Hello from qwen3.5-2b"}}]}'

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
    mock_request.body = AsyncMock(return_value=b'{"model": "qwen3.5-2b", "messages": [{"role": "user", "content": "hi"}]}')
    mock_request.app.state.http_client = mock_client

    # Mock llama_manager state: current model is qwen3.5-4b
    mock_process_state = ProcessState(status=ProcessStatusEnum.READY, model_id="qwen3.5-4b", port=8089)
    ready_state = ProcessState(status=ProcessStatusEnum.READY, model_id="qwen3.5-2b", port=8089)

    with patch("src.api.routes.inference_api.llama_manager") as mock_lm, \
         patch("src.api.routes.inference_api.check_llama_status", AsyncMock(return_value=True)):

        mock_lm.process_manager.state = mock_process_state
        mock_lm.config_manager.get_config.return_value = {"current_model": "qwen3.5-4b", "current_n_ctx": 4096}
        mock_lm.load_model_with_download = AsyncMock(return_value=ready_state)

        response = await reverse_proxy(mock_request, "chat/completions")

        assert isinstance(response, StreamingResponse)
        mock_lm.load_model_with_download.assert_awaited_once_with("qwen3.5-2b", n_ctx=8192)



@pytest.mark.asyncio
async def test_reverse_proxy_skips_hot_swap_when_same_model(monkeypatch):
    """FR-001: Verify reverse_proxy does NOT trigger hot-swap if requested model is identical to resident model."""
    monkeypatch.delenv("MOCK_LLAMA_SERVER", raising=False)

    mock_upstream_headers = Headers({"content-type": "application/json"})
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.headers = mock_upstream_headers

    async def mock_aiter_raw():
        yield b'{"choices": [{"message": {"content": "Hello"}}]}'

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
    mock_request.body = AsyncMock(return_value=b'{"model": "qwen3.5-4b", "messages": [{"role": "user", "content": "hi"}]}')
    mock_request.app.state.http_client = mock_client

    mock_process_state = ProcessState(status=ProcessStatusEnum.READY, model_id="qwen3.5-4b", port=8089)

    with patch("src.api.routes.inference_api.llama_manager") as mock_lm, \
         patch("src.api.routes.inference_api.check_llama_status", AsyncMock(return_value=True)):

        mock_lm.process_manager.state = mock_process_state
        mock_lm.config_manager.get_config.return_value = {"current_model": "qwen3.5-4b", "current_n_ctx": 4096}
        mock_lm.load_model_with_download = AsyncMock()

        response = await reverse_proxy(mock_request, "chat/completions")

        assert isinstance(response, StreamingResponse)
        mock_lm.load_model_with_download.assert_not_called()
