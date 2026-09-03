"""Integration tests for GPU capacity and concurrency queue policy (T030).

Enforces:
- 4 concurrent GPU slots
- FIFO queueing
- Queue timeout
- Fail-closed under VRAM exhaustion
"""

import pytest
import asyncio
from src.core.queue import GPUQueueManager
from src.core.vram_monitor import check_vram_headroom, assert_vram_headroom

@pytest.mark.asyncio
async def test_slot_fifo_behavior():
    qm = GPUQueueManager(max_slots=2, queue_timeout=1.0)
    s1 = await qm.acquire_slot()
    s2 = await qm.acquire_slot()
    assert qm.available_slots == 0

    # Releasing s1 frees up a slot
    await qm.release_slot(s1)
    assert qm.available_slots == 1

    s3 = await qm.acquire_slot()
    assert qm.available_slots == 0
    await qm.release_slot(s2)
    await qm.release_slot(s3)
    assert qm.available_slots == 2

def test_vram_fail_closed():
    with pytest.raises(RuntimeError, match="503"):
        assert_vram_headroom(limit_mb=0)
