"""
Unit tests for isolated BoundedSemaphore(1), 1:1 queue tickets, and pre-queue DoS rejection.

Feature: 006-model-gateway-upgrade (User Story 1, T011)
"""

import asyncio
import pytest
from fastapi import HTTPException
from src.core.queue_manager import AsyncFairQueue, QueueTicket, validate_pre_queue_prompt_limits


@pytest.mark.asyncio
async def test_isolated_model_semaphores():
    """Verify that qwen3.5-9b and qwen3.5-4b have isolated single-slot semaphores."""
    queue = AsyncFairQueue()

    # Acquire 9B slot
    ticket_9b = await queue.enqueue(model_id="qwen3.5-9b")
    await queue.acquire_slot(ticket_9b)
    assert ticket_9b.slot_held is True
    assert ticket_9b.slot_released is False

    # 4B slot can be acquired concurrently because slots are isolated per model
    ticket_4b = await queue.enqueue(model_id="qwen3.5-4b")
    await queue.acquire_slot(ticket_4b)
    assert ticket_4b.slot_held is True
    assert ticket_4b.slot_released is False

    # Second 9B request must wait/timeout
    ticket_9b_2 = await queue.enqueue(model_id="qwen3.5-9b")
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(queue.acquire_slot(ticket_9b_2), timeout=0.1)

    # Release first 9B slot
    await queue.release_slot(ticket_9b)
    assert ticket_9b.slot_released is True

    # Release 4B slot
    await queue.release_slot(ticket_4b)
    assert ticket_4b.slot_released is True


@pytest.mark.asyncio
async def test_idempotent_slot_release():
    """Verify that calling release_slot multiple times on the same ticket is idempotent."""
    queue = AsyncFairQueue()
    ticket = await queue.enqueue(model_id="qwen3.5-9b")
    await queue.acquire_slot(ticket)

    assert ticket.slot_held is True
    assert ticket.slot_released is False

    # First release
    await queue.release_slot(ticket)
    assert ticket.slot_released is True

    # Second release should not raise ValueError or corrupt bounded semaphore
    await queue.release_slot(ticket)
    assert ticket.slot_released is True


def test_language_aware_pre_queue_dos_rejection():
    """Verify pre-queue fast rejection when prompt size exceeds model limits."""
    # 4B limit: 65,536 chars
    small_prompt = "Hello world " * 100
    validate_pre_queue_prompt_limits("qwen3.5-4b", small_prompt)

    # 4B exceeding 65,536 chars
    huge_prompt_4b = "A" * 70000
    with pytest.raises(HTTPException) as exc_info_4b:
        validate_pre_queue_prompt_limits("qwen3.5-4b", huge_prompt_4b)
    assert exc_info_4b.value.status_code == 400
    assert "exceeds" in exc_info_4b.value.detail["error"]["message"]

    # 9B limit: 262,144 chars
    huge_prompt_9b = "A" * 300000
    with pytest.raises(HTTPException) as exc_info_9b:
        validate_pre_queue_prompt_limits("qwen3.5-9b", huge_prompt_9b)
    assert exc_info_9b.value.status_code == 400
    assert "exceeds" in exc_info_9b.value.detail["error"]["message"]
