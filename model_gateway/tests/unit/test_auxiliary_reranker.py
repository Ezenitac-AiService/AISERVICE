"""
Unit test for BGE Reranker v2 M3 model process spawning and healthcheck verification (US2, FR-002).
"""

import pytest
import asyncio
from src.core.process_manager import ProcessManager, ProcessStatusEnum
from src.core.auxiliary_manager import AuxiliaryModelManager


def test_process_manager_rerank_flag():
    """FR-002: Verify ProcessManager identifies bge-reranker-v2-m3 as rerank model."""
    pm = ProcessManager(port=8091)
    assert pm.is_rerank_model("bge-reranker-v2-m3") is True
    assert pm.is_embedding_model("bge-reranker-v2-m3") is False


@pytest.mark.asyncio
async def test_auxiliary_manager_ensure_rerank_resident(monkeypatch):
    """FR-002: Verify AuxiliaryModelManager ensures bge-reranker-v2-m3 resident and ready."""
    monkeypatch.setenv("MOCK_LLAMA_SERVER", "1")
    aux_mgr = AuxiliaryModelManager()

    state = await aux_mgr.ensure_rerank_resident("bge-reranker-v2-m3")
    assert state.status == ProcessStatusEnum.READY
    assert state.port == 8091
    assert state.model_id == "bge-reranker-v2-m3"
