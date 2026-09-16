"""
Contract test for Dual-LLM routing and decommissioned model rejection (T029 / US3).
Validates:
- qwen3.5-4b / fast routes to backend port 8088
- qwen3.5-9b / default / synthesis routes to backend port 8089
- Decommissioned/unsupported model (e.g. qwen3.5-2b) is rejected with HTTP 404 model_not_found
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from src.api.server import create_app
from src.core.process_manager import ProcessStatusEnum, ProcessState


@pytest.fixture
def app_client():
    app = create_app()
    with TestClient(app) as client:
        yield client, app


def test_decommissioned_model_404_model_not_found(app_client):
    """US3: Requests for decommissioned qwen3.5-2b must be rejected with HTTP 404 model_not_found."""
    client, _ = app_client
    payload = {
        "model": "qwen3.5-2b",
        "messages": [{"role": "user", "content": "Hello world"}]
    }
    resp = client.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 404, f"Expected 404 for qwen3.5-2b, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "error" in data, "Error response missing 'error' dictionary"
    assert data["error"]["code"] == "model_not_found"
    assert "qwen3.5-2b" in data["error"]["message"]


def test_unknown_model_404_model_not_found(app_client):
    """US3: Requests for non-existent model must be rejected with HTTP 404 model_not_found."""
    client, _ = app_client
    payload = {
        "model": "non-existent-llm-123",
        "messages": [{"role": "user", "content": "Hello"}]
    }
    resp = client.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "model_not_found"


@pytest.mark.asyncio
async def test_fast_model_routes_to_port_8088():
    """US3: Requests specifying 'fast' or 'qwen3.5-4b' must route to backend port 8088."""
    from src.api.routes.inference_api import _get_backend_target_port
    assert _get_backend_target_port("chat/completions", "fast") == 8088
    assert _get_backend_target_port("chat/completions", "qwen3.5-4b") == 8088
    assert _get_backend_target_port("chat/completions", "qwen3.5-4b-instruct") == 8088


@pytest.mark.asyncio
async def test_synthesis_model_routes_to_port_8089():
    """US3: Requests specifying 'default', 'synthesis', or 'qwen3.5-9b' must route to backend port 8089."""
    from src.api.routes.inference_api import _get_backend_target_port
    assert _get_backend_target_port("chat/completions", "default") == 8089
    assert _get_backend_target_port("chat/completions", "synthesis") == 8089
    assert _get_backend_target_port("chat/completions", "qwen3.5-9b") == 8089
    assert _get_backend_target_port("chat/completions", "qwen3.5-9b-instruct") == 8089
