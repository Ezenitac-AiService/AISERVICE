"""
Unit tests for OpenAI API GET /v1/models endpoint (T007 / FR-007).
Verifies that the /v1/models response matches the OpenAI Models List API contract.

Feature: 016-context-scaling-and-cleanup-fix
"""

import json
import os
import pytest
from unittest.mock import patch, MagicMock


def test_openai_models_response_schema():
    """FR-007: GET /v1/models 응답이 OpenAI 표준 JSON 구조를 준수하는지 검증."""
    from fastapi.testclient import TestClient
    from src.api.routes.inference_api import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)

    # Mock llama_manager state
    with patch("src.api.routes.inference_api.llama_manager") as mock_lm:
        mock_config = MagicMock()
        mock_config.get_config.return_value = {"current_model": "qwen3.5-4b", "current_n_ctx": 4096}
        mock_lm.config_manager = mock_config
        mock_lm.is_ready.return_value = True

        client = TestClient(app)
        response = client.get("/v1/models")

    assert response.status_code == 200
    data = response.json()

    # Validate top-level schema
    assert data["object"] == "list"
    assert "data" in data
    assert isinstance(data["data"], list)
    assert len(data["data"]) >= 6  # 카탈로그 최소 6개 모델

    # Validate each model entry
    for model_entry in data["data"]:
        assert "id" in model_entry
        assert model_entry["object"] == "model"
        assert isinstance(model_entry["created"], int)
        assert model_entry["owned_by"] == "llm-server"
        assert isinstance(model_entry["is_available"], bool)
        assert isinstance(model_entry["is_active"], bool)


def test_openai_models_contains_all_catalog_models():
    """FR-007: GET /v1/models 응답에 카탈로그 6개 모델이 모두 포함되는지 검증."""
    from fastapi.testclient import TestClient
    from src.api.routes.inference_api import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)

    with patch("src.api.routes.inference_api.llama_manager") as mock_lm:
        mock_config = MagicMock()
        mock_config.get_config.return_value = {"current_model": "qwen3.5-4b", "current_n_ctx": 4096}
        mock_lm.config_manager = mock_config
        mock_lm.is_ready.return_value = False

        client = TestClient(app)
        response = client.get("/v1/models")

    data = response.json()
    model_ids = [m["id"] for m in data["data"]]

    expected_ids = ["gemma4-e2b", "gemma4-e4b", "gemma4-12b", "qwen3.5-2b", "qwen3.5-4b", "qwen3.5-9b"]
    for eid in expected_ids:
        assert eid in model_ids, f"모델 '{eid}'가 /v1/models 응답에 누락됨"


def test_openai_models_active_model_flag():
    """FR-007: 현재 활성화된 모델이 is_active=True로 표시되는지 검증."""
    from fastapi.testclient import TestClient
    from src.api.routes.inference_api import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)

    with patch("src.api.routes.inference_api.llama_manager") as mock_lm:
        mock_config = MagicMock()
        mock_config.get_config.return_value = {"current_model": "gemma4-e2b", "current_n_ctx": 4096}
        mock_lm.config_manager = mock_config
        mock_lm.is_ready.return_value = True

        client = TestClient(app)
        response = client.get("/v1/models")

    data = response.json()
    active_models = [m for m in data["data"] if m["is_active"]]
    assert len(active_models) == 1
    assert active_models[0]["id"] == "gemma4-e2b"


def test_openai_models_no_active_when_unloaded():
    """FR-007: 백엔드 미로딩 상태에서 is_active가 모두 False인지 검증."""
    from fastapi.testclient import TestClient
    from src.api.routes.inference_api import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)

    with patch("src.api.routes.inference_api.llama_manager") as mock_lm:
        mock_config = MagicMock()
        mock_config.get_config.return_value = {"current_model": "qwen3.5-4b", "current_n_ctx": 4096}
        mock_lm.config_manager = mock_config
        mock_lm.is_ready.return_value = False  # UNLOADED

        client = TestClient(app)
        response = client.get("/v1/models")

    data = response.json()
    active_models = [m for m in data["data"] if m["is_active"]]
    assert len(active_models) == 0
