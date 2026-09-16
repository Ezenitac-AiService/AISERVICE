from unittest.mock import patch, AsyncMock
import httpx
from fastapi.testclient import TestClient

from src.api.server import create_app


def test_chat_completion_contract_schema():
    """Validates that chat completion response structure adheres to OpenAI contract specifications."""
    backend_data = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1722600000,
        "model": "qwen3.5-4b",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}
    }
    mock_resp = httpx.Response(200, json=backend_data, headers={"content-type": "application/json"})

    app = create_app()
    with patch("httpx.AsyncClient.send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = mock_resp
        with TestClient(app) as client:
            resp = client.post("/v1/chat/completions", json={
                "model": "qwen3.5-4b",
                "messages": [{"role": "user", "content": "Hello"}]
            })
            assert resp.status_code == 200
            data = resp.json()
            assert "id" in data
            assert data["object"] in ("chat.completion", "chat.completion.chunk")
            assert "choices" in data
            assert len(data["choices"]) > 0
            assert "message" in data["choices"][0] or "delta" in data["choices"][0]
