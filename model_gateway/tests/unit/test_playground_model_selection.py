"""
Unit Test Suite for AI Playground Dynamic Model Selection & Server Model Sync (049-playground-model-selection).
Strict Anti-Mock Real Execution per Constitution v1.5.2.
"""

import pytest
from fastapi.testclient import TestClient
from src.api.server import app

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_capabilities_returns_current_and_available_models(client):
    """FR-002, FR-003: GET /dashboard/api/capabilities returns active serving model & available model list."""
    res = client.get("/dashboard/api/capabilities")
    assert res.status_code == 200
    data = res.json()
    assert "current_model" in data
    assert "available_models" in data
    assert isinstance(data["available_models"], list)


def test_playground_stream_handles_custom_model_parameter(client):
    """FR-004, FR-006: POST /dashboard/api/playground/stream accepts selected model from dropdown."""
    res = client.post("/dashboard/api/playground/stream", json={
        "model": "qwen3.5-4b",
        "prompt": "Test model selection prompt",
        "system_prompt": "You are a test bot",
        "max_tokens": 50
    })
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]
    assert "data:" in res.text or "[DONE]" in res.text
