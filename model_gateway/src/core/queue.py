#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GPU Inference FIFO Queue Manager (SSOT).
Enforces:
- Max concurrent GPU slots: 4 (RTX 3060 12GB)
- FIFO queueing for requests beyond slot limit
- Queue timeout: 60s (raises TimeoutError/429)
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Optional


class GPUQueueManager:
    """Manages GPU concurrent slot allocation and FIFO waiting queue."""

    def __init__(self, max_slots: int = 4, queue_timeout: float = 60.0) -> None:
        self.max_slots = max_slots
        self.queue_timeout = queue_timeout
        self._semaphore = asyncio.Semaphore(max_slots)
        self._active_slots: set[str] = set()
        self._lock = asyncio.Lock()

    @property
    def available_slots(self) -> int:
        return max(0, self.max_slots - len(self._active_slots))

    @property
    def active_slots(self) -> int:
        return len(self._active_slots)

    async def acquire_slot(self, timeout: Optional[float] = None) -> str:
        """Acquire a GPU inference slot, waiting in FIFO order up to queue_timeout."""
        wait_time = timeout if timeout is not None else self.queue_timeout

        try:
            # Wait for available slot with timeout
            await asyncio.wait_for(self._semaphore.acquire(), timeout=wait_time)
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"GPU queue wait timeout ({wait_time}s) exceeded. Server is at maximum capacity (4 slots)."
            )

        slot_id = f"slot_{uuid.uuid4().hex[:8]}"
        async with self._lock:
            self._active_slots.add(slot_id)

        return slot_id

    async def release_slot(self, slot_id: str) -> None:
        """Release an acquired slot and notify next waiting request."""
        async with self._lock:
            if slot_id in self._active_slots:
                self._active_slots.remove(slot_id)
                self._semaphore.release()


_global_queue_manager: Optional[GPUQueueManager] = None


def get_gpu_queue_manager() -> GPUQueueManager:
    global _global_queue_manager
    if _global_queue_manager is None:
        max_slots = int(os.environ.get("MAX_GPU_CONCURRENT_SLOTS", 4))
        timeout = float(os.environ.get("QUEUE_TIMEOUT_SECONDS", 60.0))
        _global_queue_manager = GPUQueueManager(max_slots=max_slots, queue_timeout=timeout)
    return _global_queue_manager
