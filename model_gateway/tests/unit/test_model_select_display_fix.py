"""
Unit Test Suite for Dynamic Model Select Dropdown & ConfigManager Catalog Bug Fix (051-fix-model-select-display).
Strict Anti-Mock Real Execution per Constitution v1.5.2.
"""

import pytest
from fastapi.testclient import TestClient
from src.api.server import app
from src.core.config_manager import ConfigManager

client = TestClient(app)


def test_config_manager_catalog_cache_fix():
    """FR-001: Test that ConfigManager catalog loader loads catalog entries without sticky empty dict."""
    cm = ConfigManager()
    cm.invalidate_all_caches()
    
    catalog = cm.get_model_catalog()
    assert isinstance(catalog, dict)
    assert len(catalog) > 0, "Catalog should contain dynamic models from model_catalog.json"
    assert "qwen3.5-4b" in catalog


def test_capabilities_returns_dynamic_available_models():
    """FR-002: Test that GET /dashboard/api/capabilities returns dynamic available_models list."""
    res = client.get("/dashboard/api/capabilities")
    assert res.status_code == 200
    data = res.json()
    assert "available_models" in data
    assert isinstance(data["available_models"], list)
    assert len(data["available_models"]) > 0, "available_models should not be empty"
    
    cm = ConfigManager()
    expected_models = list(cm.get_model_catalog().keys())
    assert data["available_models"] == expected_models
