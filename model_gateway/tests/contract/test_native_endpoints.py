"""
Contract and Integration test for 4 native endpoints (T010 / US1).
Endpoints:
1. POST /v1/chat/completions
2. POST /v1/embeddings
3. POST /v1/rerank
4. GET /health/readiness
"""

import pytest
from fastapi.testclient import TestClient
from src.api.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_readiness_endpoint_contract(client):
    """Verify /health/readiness contract compliance."""
    response = client.get("/health/readiness")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "status" in data
    assert "models" in data


def test_chat_completions_contract_validation(client):
    """Verify /v1/chat/completions request validation."""
    # Missing messages -> 422
    resp = client.post("/v1/chat/completions", json={"model": "qwen3.5-9b"})
    assert resp.status_code == 422

    # Invalid model -> 400 or 422
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "non-existent-model", "messages": [{"role": "user", "content": "hi"}]}
    )
    assert resp.status_code in (400, 404, 422)


def test_embeddings_contract_validation(client):
    """Verify /v1/embeddings accepts valid input."""
    resp = client.post("/v1/embeddings", json={"input": "test embedding text"})
    # Even if model is omitted, should either succeed (auto-inject) or proxy
    assert resp.status_code != 404


def test_rerank_contract_validation(client):
    """Verify /v1/rerank accepts query and documents."""
    resp = client.post(
        "/v1/rerank",
        json={
            "query": "What is Python?",
            "documents": ["Python is a language", "Apples are fruit"]
        }
    )
    assert resp.status_code != 404
