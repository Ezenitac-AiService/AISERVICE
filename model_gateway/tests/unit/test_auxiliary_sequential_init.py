"""
Unit test for AuxiliaryModelManager sequential initialization (US1, FR-004).
Verifies embedding model starts and completes before reranker model initialization begins.
"""

import pytest
import asyncio
from src.core.process_manager import ProcessStatusEnum, ProcessState
from src.core.auxiliary_manager import AuxiliaryModelManager


@pytest.mark.asyncio
async def test_auxiliary_sequential_initialization_order(monkeypatch):
    """FR-004: Verify embedding is initialized before reranker starts in start_auto_startup_and_recovery."""
    monkeypatch.setenv("MOCK_LLAMA_SERVER", "1")
    aux_mgr = AuxiliaryModelManager()

    execution_order = []

    async def mock_ensure_embedding(model_id="bge-m3", n_ctx=8192):
        execution_order.append("embedding_start")
        await asyncio.sleep(0.05)
        execution_order.append("embedding_end")
        aux_mgr.embedding_pm.state = ProcessState(status=ProcessStatusEnum.READY, port=8090)
        return aux_mgr.embedding_pm.state

    async def mock_ensure_rerank(model_id="bge-reranker-v2-m3", n_ctx=8192):
        execution_order.append("rerank_start")
        await asyncio.sleep(0.05)
        execution_order.append("rerank_end")
        aux_mgr.rerank_pm.state = ProcessState(status=ProcessStatusEnum.READY, port=8091)
        return aux_mgr.rerank_pm.state

    monkeypatch.setattr(aux_mgr, "ensure_embedding_resident", mock_ensure_embedding)
    monkeypatch.setattr(aux_mgr, "ensure_rerank_resident", mock_ensure_rerank)

    # Trigger initialization helper
    await aux_mgr.run_sequential_startup()

    assert execution_order == [
        "embedding_start",
        "embedding_end",
        "rerank_start",
        "rerank_end"
    ]
