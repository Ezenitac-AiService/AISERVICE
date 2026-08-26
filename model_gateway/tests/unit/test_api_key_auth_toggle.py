"""
Unit/E2E Test Suite for API Key Auth Toggle & Metrics (043-api-key-auth-toggle).
Strict Anti-Mock Real Execution per Constitution v1.4.0.
"""

import pytest
from fastapi.testclient import TestClient
from src.api.server import app
from src.core.config_manager import ConfigManager
from src.core.metrics_db import metrics_db

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_api_key_auth_toggle_flow(client):
    cm = ConfigManager()
    server_cfg = cm.get_server_config()
    admin_secret = server_cfg.get("admin_secret", "aiservice")

    # 1. Enable API Key Enforcement Mode (ON)
    res_toggle_on = client.post(
        "/dashboard/api/config",
        json={"api_key_enabled": True},
        headers={"X-Admin-Secret": admin_secret}
    )
    assert res_toggle_on.status_code == 200
    assert "ENABLED" in res_toggle_on.json()["message"]

    # 2. Request /v1/chat/completions without API Key -> Expected HTTP 401 Unauthorized
    res_unauth = client.post(
        "/dashboard/api/playground",
        json={"prompt": "test prompt"}
    )
    # Note: /v1/ endpoint check
    res_unauth_v1 = client.post(
        "/v1/chat/completions",
        json={"model": "qwen3.5-4b", "messages": [{"role": "user", "content": "hi"}]}
    )
    assert res_unauth_v1.status_code == 401, f"Expected HTTP 401, got {res_unauth_v1.status_code}"

    # 3. Request /v1/chat/completions with valid test key -> Expected HTTP 200 OK
    res_auth_v1 = client.post(
        "/v1/chat/completions",
        json={"model": "qwen3.5-4b", "messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": "Bearer sk-vllm-test"}
    )
    assert res_auth_v1.status_code in [200, 503], f"Expected 200/503 (ready state), got {res_auth_v1.status_code}"

    # 4. Disable API Key Enforcement Mode (OFF)
    res_toggle_off = client.post(
        "/dashboard/api/config",
        json={"api_key_enabled": False},
        headers={"X-Admin-Secret": admin_secret}
    )
    assert res_toggle_off.status_code == 200
    assert "DISABLED" in res_toggle_off.json()["message"]

    # 5. Retrieve Metrics
    res_metrics = client.get("/dashboard/api/keys/metrics")
    assert res_metrics.status_code == 200
    data = res_metrics.json()
    assert "metrics" in data
    assert "top_5" in data

    # 6. CSV Export
    res_csv = client.get("/dashboard/api/keys/export/csv")
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers.get("content-type", "")
