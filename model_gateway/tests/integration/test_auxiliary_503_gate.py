"""
Integration test for Reverse Proxy 503 Gate (US2, FR-002, SC-002).
Verifies that when auxiliary models are in DISABLED or ERROR state, reverse_proxy returns 503
with explicit error details instead of attempting proxy forwarding and returning 404.
"""

import pytest
from fastapi.testclient import TestClient
from src.api.server import app
from src.core.process_manager import ProcessStatusEnum, ProcessState
from src.core.auxiliary_manager import auxiliary_manager


@pytest.fixture
def client():
    return TestClient(app)


def test_reverse_proxy_rerank_disabled_returns_503(client, monkeypatch):
    """FR-002 & SC-002: Verify POST /v1/rerank returns 503 (not 404) when reranker is DISABLED."""
    auxiliary_manager.rerank_pm.state = ProcessState(
        status=ProcessStatusEnum.DISABLED,
        port=8091,
        model_id="bge-reranker-v2-m3",
        error_message="Reranker disabled due to 3 consecutive crashes."
    )

    async def mock_ensure_rerank(model_id="bge-reranker-v2-m3", n_ctx=8192):
        return auxiliary_manager.rerank_pm.state

    monkeypatch.setattr(auxiliary_manager, "ensure_rerank_resident", mock_ensure_rerank)

    payload = {
        "model": "bge-reranker-v2-m3",
        "query": "What is vllm_serv?",
        "documents": ["vllm_serv is a high-performance inference engine."]
    }

    resp = client.post("/v1/rerank", json=payload)
    assert resp.status_code == 503
    data = resp.json()
    assert "Reranker model is not available" in data["detail"] or "disabled" in data["detail"].lower()


def test_reverse_proxy_embedding_disabled_returns_503(client, monkeypatch):
    """FR-002 & SC-002: Verify POST /v1/embeddings returns 503 (not 404) when embedding is DISABLED."""
    auxiliary_manager.embedding_pm.state = ProcessState(
        status=ProcessStatusEnum.DISABLED,
        port=8090,
        model_id="bge-m3",
        error_message="Embedding disabled due to 3 consecutive crashes."
    )

    async def mock_ensure_embedding(model_id="bge-m3", n_ctx=8192):
        return auxiliary_manager.embedding_pm.state

    monkeypatch.setattr(auxiliary_manager, "ensure_embedding_resident", mock_ensure_embedding)

    payload = {
        "model": "bge-m3",
        "input": "test embedding text"
    }

    resp = client.post("/v1/embeddings", json=payload)
    assert resp.status_code == 503
    data = resp.json()
    assert "Embedding model is not available" in data["detail"] or "disabled" in data["detail"].lower()
