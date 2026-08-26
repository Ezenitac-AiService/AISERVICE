"""
Unit test for BGE M3 embedding model process spawning and /v1/embeddings inference (US1, FR-001).
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch
from src.core.process_manager import ProcessManager, ProcessStatusEnum
from src.core.auxiliary_manager import AuxiliaryModelManager


def test_process_manager_embedding_flag():
    """FR-001: Verify ProcessManager appends --embedding flag when spawning bge-m3."""
    pm = ProcessManager(port=8090)
    assert pm.is_embedding_model("bge-m3") is True
    assert pm.is_rerank_model("bge-m3") is False


@pytest.mark.asyncio
async def test_auxiliary_manager_ensure_embedding_resident(monkeypatch):
    """FR-001: Verify AuxiliaryModelManager ensures bge-m3 resident and ready."""
    monkeypatch.setenv("MOCK_LLAMA_SERVER", "1")
    aux_mgr = AuxiliaryModelManager()

    state = await aux_mgr.ensure_embedding_resident("bge-m3")
    assert state.status == ProcessStatusEnum.READY
    assert state.port == 8090
    assert state.model_id == "bge-m3"
