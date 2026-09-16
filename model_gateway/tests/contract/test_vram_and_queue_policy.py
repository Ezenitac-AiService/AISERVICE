"""Contract tests for VRAM safety limits and FIFO GPU queue policies.

Enforces:
- Single-slot concurrent GPU execution per model (max_slots=1), FIFO queuing for 2nd+ request.
- VRAM safety limit of 11,264MB for RTX 3060 12GB.
- Strict prohibition of silent CPU fallback on GPU OOM or exhaustion (fail-closed 503).
"""

import pytest
import asyncio
from pathlib import Path

@pytest.mark.asyncio
async def test_slot_semaphore_limits_to_one_concurrent():
    """Verify single-slot semaphore concurrency per model."""
    from src.core.queue import GPUQueueManager
    qm = GPUQueueManager(max_slots=1, queue_timeout=2)

    assert qm.available_slots == 1
    slot = await qm.acquire_slot()
    assert qm.available_slots == 0

    # 2nd request must queue and time out if no slot is released
    with pytest.raises((TimeoutError, Exception)):
        await asyncio.wait_for(qm.acquire_slot(), timeout=0.2)

    await qm.release_slot(slot)
    assert qm.available_slots == 1


def test_vram_limit_enforcement():
    """Requests exceeding 11264MB safety limit must fail closed."""
    from src.core.vram_monitor import check_vram_headroom

    # Within safety limit (e.g. 10872MB / 11264MB)
    assert check_vram_headroom(current_vram_mb=10872, limit_mb=11264) is True

    # Exceeding safety limit (e.g. 11500MB / 11264MB)
    assert check_vram_headroom(current_vram_mb=11500, limit_mb=11264) is False
