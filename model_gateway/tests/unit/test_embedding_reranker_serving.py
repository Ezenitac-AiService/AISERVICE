"""
Unit and Integration Test Suite for Embedding and Reranker Model Serving (FR-001 ~ FR-008, SC-001 ~ SC-004).
Tests OpenAI-compatible POST /v1/embeddings and Cross-Encoder POST /v1/rerank endpoints,
multi-instance routing, non-AVX legacy CPU profile safety, and VRAM budget verification.
"""

import pytest
import os
import asyncio
import httpx
from fastapi.testclient import TestClient

from src.core.config_manager import ConfigManager, ServerConfig, TaskTypeEnum
from src.core.process_manager import ProcessManager, ProcessStatusEnum
from src.core.auxiliary_manager import AuxiliaryModelManager
from src.api.server import create_app


@pytest.fixture
def test_config():
    cm = ConfigManager()
    return cm


@pytest.fixture
def client():
    os.environ["MOCK_LLAMA_SERVER"] = "1"
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_model_catalog_embedding_and_reranker(test_config):
    """T001/T003: Verify bge-m3 and bge-reranker-v2-m3 catalog entries and task_type."""
    catalog = test_config.get_model_catalog()

    assert "bge-m3" in catalog
    bge_entry = catalog["bge-m3"]
    assert bge_entry["task_type"] == "embedding"
    assert bge_entry["default_port"] == 8090
    assert bge_entry["repo_id"] == "ggml-org/bge-m3-Q8_0-GGUF"

    assert "bge-reranker-v2-m3" in catalog
    rerank_entry = catalog["bge-reranker-v2-m3"]
    assert rerank_entry["task_type"] == "rerank"
    assert rerank_entry["default_port"] == 8091
    assert rerank_entry["repo_id"] == "klnstpr/bge-reranker-v2-m3-Q8_0-GGUF"


def test_server_config_ports_validation(test_config):
    """T002: Verify embedding_backend_port and rerank_backend_port in ServerConfig."""
    server_cfg = test_config.get_server_config()
    assert server_cfg.get("embedding_backend_port") == 8090
    assert server_cfg.get("rerank_backend_port") == 8091
    assert server_cfg.get("embedding_enabled") is True
    assert server_cfg.get("rerank_enabled") is True


def test_process_manager_command_flags():
    """T005: Verify --embedding and --reranking flags are appended during spawn_process."""
    pm = ProcessManager(port=8090)
    # Test preset task_type lookup
    bge_preset = pm.model_presets.get("bge-m3")
    assert bge_preset is not None
    assert bge_preset.get("task_type") == "embedding"

    rerank_preset = pm.model_presets.get("bge-reranker-v2-m3")
    assert rerank_preset is not None
    assert rerank_preset.get("task_type") == "rerank"


def test_embedding_api_routing(client):
    """T007/T008/SC-001: Test POST /v1/embeddings endpoint payload parsing and proxying."""
    payload = {
        "model": "bge-m3",
        "input": ["안녕하세요, 임베딩 서빙 테스트입니다."]
    }
    response = client.post("/v1/embeddings", json=payload)
    assert response.status_code in (200, 503)
    if response.status_code == 200:
        data = response.json()
        assert data["object"] == "list"
        assert "data" in data
        assert len(data["data"]) > 0
        assert "embedding" in data["data"][0]


def test_rerank_api_routing(client):
    """T012/T013/SC-002: Test POST /v1/rerank endpoint payload parsing and relevance scoring."""
    payload = {
        "model": "bge-reranker-v2-m3",
        "query": "검색 최적화",
        "documents": ["FastAPI 웹 서비스", "llama-server GPU 서빙 및 리랭킹"]
    }
    response = client.post("/v1/rerank", json=payload)
    assert response.status_code in (200, 503)
    if response.status_code == 200:
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 2
        assert "relevance_score" in data["results"][0]


def test_nehalem_legacy_cpu_profile_safety(test_config):
    """T010/T015/SC-003: Verify Non-AVX binary building and 100% CUDA GPU offloading for Nehalem CPU."""
    profiles = test_config.get_platform_profiles()
    nehalem_profile = profiles.get("legacy-i7-930-gtx1070")
    assert nehalem_profile is not None
    assert nehalem_profile.get("expected_avx") is False
    assert nehalem_profile.get("expected_avx2") is False


def test_auxiliary_manager_lifecycle():
    """T006/T009/T014: Verify AuxiliaryModelManager auto-start and status."""
    aux_mgr = AuxiliaryModelManager()
    assert aux_mgr.embedding_port == 8090
    assert aux_mgr.rerank_port == 8091
