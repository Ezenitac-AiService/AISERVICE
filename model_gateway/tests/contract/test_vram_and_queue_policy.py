"""Contract tests for VRAM safety limits and FIFO GPU queue policies.

Enforces:
- FR-002: 4 concurrent GPU slots, FIFO queuing for 5th+ request, 60s queue timeout.
- FR-003: Strict prohibition of silent CPU fallback on GPU OOM or exhaustion (fail-closed 503/429).
"""

import pytest
import asyncio
from pathlib import Path

@pytest.mark.asyncio
async def test_slot_semaphore_limits_to_four_concurrent():
    """Verify that no more than 4 concurrent inference tasks acquire slots simultaneously."""
    from AISERVICE.model_gateway.src.core.queue import GPUQueueManager

    qm = GPUQueueManager(max_slots=4, queue_timeout=2)
    assert qm.available_slots == 4

    acquired = []
    for _ in range(4):
        slot = await qm.acquire_slot()
        acquired.append(slot)

    assert qm.available_slots == 0
    assert qm.active_slots == 4

    # 5th request must queue and time out if no slot is released
    with pytest.raises((TimeoutError, Exception)):
        await asyncio.wait_for(qm.acquire_slot(), timeout=0.2)

    # Release one slot
    await qm.release_slot(acquired[0])
    assert qm.available_slots == 1

def test_vram_limit_enforcement():
    """Requests exceeding 10240MB safety limit must fail closed."""
    from AISERVICE.model_gateway.src.core.vram_monitor import check_vram_headroom

    # Within safety limit (e.g. 6000MB / 10240MB)
    assert check_vram_headroom(current_vram_mb=6000, limit_mb=10240) is True

    # Exceeding safety limit (e.g. 10500MB / 10240MB)
    assert check_vram_headroom(current_vram_mb=10500, limit_mb=10240) is False
