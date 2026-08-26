"""
Unit test for AuxiliaryModelManager Circuit Breaker logic (US1, FR-001, FR-003).
Verifies consecutive crash tracking, transition to DISABLED status after max crashes (3),
and crash counter reset on READY status.
"""

import pytest
import asyncio
from src.core.process_manager import ProcessManager, ProcessStatusEnum, ProcessState
from src.core.auxiliary_manager import AuxiliaryModelManager


@pytest.mark.asyncio
async def test_auxiliary_circuit_breaker_disabled_after_max_crashes(monkeypatch):
    """FR-001: Verify consecutive crashes transition process state to DISABLED after max retries."""
    monkeypatch.delenv("MOCK_LLAMA_SERVER", raising=False)
    aux_mgr = AuxiliaryModelManager()
    aux_mgr.max_consecutive_crashes = 3

    # Set up mock process that has exited
    mock_proc = asyncio.subprocess.Process
    mock_proc.returncode = 1

    # Simulate Rerank process in READY status but process returncode is set (crashed)
    aux_mgr.rerank_pm.state = ProcessState(status=ProcessStatusEnum.READY, port=8091)
    aux_mgr.rerank_pm.process = mock_proc

    # Mock ensure_rerank_resident to fail (return ERROR state)
    async def mock_ensure_rerank_resident(model_id="bge-reranker-v2-m3", n_ctx=8192):
        aux_mgr.rerank_pm.state = ProcessState(status=ProcessStatusEnum.ERROR, port=8091, error_message="OOM")
        return aux_mgr.rerank_pm.state

    monkeypatch.setattr(aux_mgr, "ensure_rerank_resident", mock_ensure_rerank_resident)

    # Run single iteration of crash check
    await aux_mgr.check_and_recover_crashes()
    assert aux_mgr.rerank_consecutive_crashes == 1
    assert aux_mgr.rerank_pm.state.status == ProcessStatusEnum.ERROR

    # Second crash
    aux_mgr.rerank_pm.state = ProcessState(status=ProcessStatusEnum.READY, port=8091)
    await aux_mgr.check_and_recover_crashes()
    assert aux_mgr.rerank_consecutive_crashes == 2

    # Third crash -> should trigger DISABLED
    aux_mgr.rerank_pm.state = ProcessState(status=ProcessStatusEnum.READY, port=8091)
    await aux_mgr.check_and_recover_crashes()
    assert aux_mgr.rerank_consecutive_crashes == 3
    assert aux_mgr.rerank_pm.state.status == ProcessStatusEnum.DISABLED

    # Fourth check -> should skip recovery because it's DISABLED
    await aux_mgr.check_and_recover_crashes()
    assert aux_mgr.rerank_consecutive_crashes == 3
    assert aux_mgr.rerank_pm.state.status == ProcessStatusEnum.DISABLED


@pytest.mark.asyncio
async def test_auxiliary_circuit_breaker_counter_reset_on_ready():
    """FR-003: Verify consecutive crash counter resets to 0 when model reaches READY."""
    aux_mgr = AuxiliaryModelManager()
    aux_mgr.rerank_consecutive_crashes = 2

    # Setting process status to READY should reset counter
    aux_mgr.rerank_pm.state = ProcessState(status=ProcessStatusEnum.READY, port=8091)
    aux_mgr._reset_crash_counter_if_ready("rerank")
    assert aux_mgr.rerank_consecutive_crashes == 0
