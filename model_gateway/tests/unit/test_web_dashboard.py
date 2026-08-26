"""Unit and contract tests for Web Dashboard API endpoints (040-ufw-sudo-detection-fix).

Tests GET /dashboard/api/benchmark/profiles and POST /dashboard/api/benchmark/rerun.
"""

import os
import json
import pytest
from fastapi.testclient import TestClient
from src.api.server import create_app

app = create_app()
client = TestClient(app)


def test_get_benchmark_profiles_endpoint():
    """Verify GET /dashboard/api/benchmark/profiles endpoint response structure."""
    response = client.get("/dashboard/api/benchmark/profiles")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    if data["status"] == "success":
        assert "data" in data


def test_trigger_benchmark_rerun_unauthorized():
    """Verify POST /dashboard/api/benchmark/rerun requires admin secret auth."""
    response = client.post("/dashboard/api/benchmark/rerun")
    assert response.status_code == 401


def test_trigger_benchmark_rerun_authorized():
    """Verify POST /dashboard/api/benchmark/rerun accepts valid admin secret."""
    from src.core.config_manager import ConfigManager
    secret = ConfigManager().get_server_config().get("admin_secret", "aiservice")

    response = client.post(
        "/dashboard/api/benchmark/rerun",
        headers={"X-Admin-Secret": secret}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["accepted", "running"]
    assert "task_id" in data
