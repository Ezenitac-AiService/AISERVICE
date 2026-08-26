"""
Integration test for Proxy Preflight Guard returning 503 when backend is unready (US3, FR-007, SC-005).
"""

import pytest
import httpx
from fastapi.testclient import TestClient
from src.api.server import create_app
from src.core.llama_manager import llama_manager


def test_preflight_guard_unready_backend(monkeypatch):
    """FR-007: Verify reverse proxy returns 503 Service Unavailable when llama_manager is not ready."""
    monkeypatch.setattr(llama_manager, "is_ready", lambda: False)
    app = create_app()
    client = TestClient(app)

    response = client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "Hello"}]})
    assert response.status_code == 503
    assert "loading" in response.json()["detail"].lower() or "unloaded" in response.json()["detail"].lower() or "unreachable" in response.json()["detail"].lower()
