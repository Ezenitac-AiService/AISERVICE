import json
import pytest
from fastapi.testclient import TestClient

from src.api.server import create_app


def test_chat_completion_contract_schema():
    """Validates that chat completion response structure adheres to OpenAI contract specifications."""
    import os
    os.environ["MOCK_LLAMA_SERVER"] = "1"
    try:
        app = create_app()
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
    finally:
        os.environ.pop("MOCK_LLAMA_SERVER", None)

