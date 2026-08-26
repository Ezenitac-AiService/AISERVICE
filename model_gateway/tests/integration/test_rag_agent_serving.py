import pytest
from fastapi.testclient import TestClient
from src.api.server import create_app

def test_rag_agent_serving_models_endpoint():
    app = create_app()
    client = TestClient(app)
    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert isinstance(data["data"], list)
    assert len(data["data"]) >= 6

def test_rag_agent_serving_chat_unloaded_503():
    app = create_app()
    client = TestClient(app)
    response = client.post("/v1/chat/completions", json={
        "model": "qwen3.5-4b",
        "messages": [{"role": "user", "content": "Hello"}]
    })
    # Since llama-server process is not running in test, 503 Service Unavailable is expected
    assert response.status_code == 503
