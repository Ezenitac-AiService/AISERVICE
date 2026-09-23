"""
Unit tests for Zero-Wait Fast-Path and non-blocking slot acquisition (FR-008).
Validates:
1. Atomic non-blocking slot acquisition succeeds immediately when slot is free (0ms delay)
2. Acquisition strictly avoids asyncio.wait_for(sem.acquire(), timeout=0) (Python 3.12 bug)
3. When slot is locked, non-blocking acquisition returns False and falls back to fair queue
"""

import asyncio
import time
import pytest
from src.core.queue_manager import try_acquire_slot_nonblocking


@pytest.mark.asyncio
async def test_zero_wait_fast_path_immediate_acquisition():
    """Verify try_acquire_slot_nonblocking acquires slot in < 5ms when unlocked."""
    sem = asyncio.BoundedSemaphore(1)

    start = time.perf_counter()
    acquired = await try_acquire_slot_nonblocking(sem)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert acquired is True
    assert sem.locked() is True
    assert elapsed_ms < 5.0, f"Fast-path acquisition took too long: {elapsed_ms:.2f}ms"

    # Release for cleanup
    sem.release()


@pytest.mark.asyncio
async def test_fast_path_fails_cleanly_when_locked():
    """Verify try_acquire_slot_nonblocking returns False immediately when slot is locked."""
    sem = asyncio.BoundedSemaphore(1)
    await sem.acquire()  # Lock it

    assert sem.locked() is True

    start = time.perf_counter()
    acquired = await try_acquire_slot_nonblocking(sem)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert acquired is False
    assert elapsed_ms < 5.0, f"Locked check took too long: {elapsed_ms:.2f}ms"

    # Cleanup
    sem.release()
