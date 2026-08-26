"""
Unit Test Suite for Playground API Key Authentication & Security Mode Enforcement (050-playground-api-key-auth).
Strict Anti-Mock Real Execution per Constitution v1.5.2.
"""

import pytest
from fastapi.testclient import TestClient
from src.api.server import app
from src.core.config_manager import ConfigManager

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_capabilities_includes_api_key_enabled(client):
    """FR-001: GET /dashboard/api/capabilities includes api_key_enabled field."""
    res = client.get("/dashboard/api/capabilities")
    assert res.status_code == 200
    data = res.json()
    assert "api_key_enabled" in data
    assert isinstance(data["api_key_enabled"], bool)


def test_playground_api_key_mode_enforcement(client):
    """FR-003, FR-004: Test 401 rejection when Security Mode is ON without valid API Key."""
    cm = ConfigManager()
    server_cfg = cm.get_server_config()
    
    # 1. Enable API key required mode temporarily
    server_cfg["api_key_enabled"] = True
    cm.save_server_config(server_cfg)
    
    try:
        # Request without API key -> Should fail with 401
        res_no_key = client.post("/dashboard/api/playground/stream", json={
            "prompt": "Test unauthorized prompt",
            "max_tokens": 10
        })
        assert res_no_key.status_code == 401
        
        # Request with valid test key -> Should succeed
        res_valid_key = client.post("/dashboard/api/playground/stream", json={
            "api_key": "sk-vllm-test",
            "prompt": "Test authorized prompt",
            "max_tokens": 10
        })
        assert res_valid_key.status_code == 200

    finally:
        # Restore public mode
        server_cfg["api_key_enabled"] = False
        cm.save_server_config(server_cfg)
