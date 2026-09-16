"""
Integration test for client disconnect and RAII slot recovery without deadlock.

Feature: 006-model-gateway-upgrade (User Story 1, T013)
CWE-833 Deadlock Elimination Guard
"""

import asyncio
import pytest
from src.core.queue_manager import AsyncFairQueue, TicketStatus


@pytest.mark.asyncio
async def test_client_disconnect_raii_slot_recovery():
    """Verify that when a client abruptly disconnects, the acquired slot is released and does not deadlock subsequent requests."""
    queue = AsyncFairQueue()

    # 1. First client enqueues and acquires slot
    ticket1 = await queue.enqueue(model_id="qwen3.5-9b")
    await queue.acquire_slot(ticket1)
    assert ticket1.slot_held is True
    assert ticket1.slot_released is False
    assert queue.active_count == 1

    # 2. Simulate client disconnect: status set to DISCONNECTED, cancelled
    ticket1.status = TicketStatus.DISCONNECTED

    # 3. RAII cleanup runs in finally block
    await queue.release_slot(ticket1)
    assert ticket1.slot_released is True
    assert queue.active_count == 0

    # 4. Second client arrives immediately - MUST be able to acquire slot without hanging or timing out
    ticket2 = await queue.enqueue(model_id="qwen3.5-9b")
    try:
        await asyncio.wait_for(queue.acquire_slot(ticket2), timeout=1.0)
        assert ticket2.slot_held is True
        assert ticket2.slot_released is False
        assert queue.active_count == 1
    finally:
        await queue.release_slot(ticket2)
        assert ticket2.slot_released is True
        assert queue.active_count == 0


@pytest.mark.asyncio
async def test_cancelled_ticket_slot_release_idempotence():
    """Verify that calling release_slot on a CANCELLED ticket releases the slot cleanly."""
    queue = AsyncFairQueue()

    ticket = await queue.enqueue(model_id="qwen3.5-4b")
    await queue.acquire_slot(ticket)
    assert ticket.slot_held is True

    # Cancel ticket
    await queue.cancel(ticket.ticket_id)
    assert ticket.status == TicketStatus.CANCELLED

    # Cleanup finally block
    await queue.release_slot(ticket)
    assert ticket.slot_released is True
    assert queue.active_count == 0
