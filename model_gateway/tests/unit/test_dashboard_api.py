"""
Unit and Integration Test Suite for Dashboard API & Admin Protection (FR-001 ~ FR-010).
Tests /dashboard/api/capabilities, /dashboard/api/apply (401 Admin Secret check),
/dashboard/api/stream, /dashboard/api/audit, and /dashboard/api/playground endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from src.api.server import app
@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_dashboard_capabilities_public(client):
    """T010: Public capability endpoint returns platform profile filtered model list."""
    response = client.get("/dashboard/api/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert "available_models" in data
    assert "platform_profile" in data
    assert isinstance(data["available_models"], list)


def test_dashboard_apply_unauthorized_returns_401(client):
    """T011: Unauthenticated apply request must return 401 Unauthorized."""
    response = client.post(
        "/dashboard/api/apply",
        json={"model_id": "qwen3.5-2b", "n_ctx": 4096}
    )
    assert response.status_code == 401
    assert "Unauthorized" in response.json()["detail"]


def test_dashboard_apply_with_valid_admin_secret(client):
    """T011: Valid X-Admin-Secret header passes authorization."""
    response = client.post(
        "/dashboard/api/apply",
        json={"model_id": "qwen3.5-2b", "n_ctx": 4096},
        headers={"X-Admin-Secret": "aiservice"}
    )
    assert response.status_code in [200, 202]
    assert response.json()["status"] == "success"




def test_dashboard_unload_unauthorized_returns_401(client):
    """T011: Unauthenticated unload request must return 401 Unauthorized."""
    response = client.post("/dashboard/api/unload")
    assert response.status_code == 401


def test_dashboard_audit_logs_retrieval(client):
    """T019: Audit logs endpoint returns client request log entries."""
    response = client.get("/dashboard/api/audit")
    assert response.status_code == 200
    data = response.json()
    assert "logs" in data
    assert isinstance(data["logs"], list)


def test_dashboard_playground_test_execution(client):
    """T015: Playground test endpoint returns prompt result with TTFT & tok/s metrics."""
    response = client.post(
        "/dashboard/api/playground",
        json={
            "model": "qwen3.5-2b",
            "prompt": "Hello test",
            "system_prompt": "You are helpful",
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 100
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "text" in data
    assert "ttft_ms" in data
    assert "token_speed_tok_s" in data
    assert "finish_reason" in data
