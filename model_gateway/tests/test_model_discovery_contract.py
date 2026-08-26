import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from src.api.server import app

client = TestClient(app)

def test_get_models_contract():
    """Verify GET /v1/models returns active resident model with context metadata."""
    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert isinstance(data["data"], list)
    
    # Check that qwen3.5-2b is present and active
    model_ids = [m["id"] for m in data["data"]]
    assert any("qwen3.5-2b" in m_id.lower() or "bge" in m_id.lower() for m_id in model_ids)

def test_get_profile_contract():
    """Verify GET /v1/profile returns hardware VRAM status and active resident model."""
    response = client.get("/v1/profile")
    assert response.status_code == 200
    data = response.json()
    assert "active_model" in data
    assert "current_n_ctx" in data
    assert "vram_total_mb" in data
    assert "single_model_mode" in data
    assert data["current_n_ctx"] == 16384
    assert data["active_model"] == "qwen3.5-2b"
