"""
Priority Preemption Scheduler for Model Gateway (FR-011, FR-013).
Ensures high-priority interactive chatbot requests preempt low-priority background batch tasks.
"""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any


class PriorityPreemptionScheduler:
    """Manages GPU inference concurrency with priority scheduling and mutual exclusion."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._high_priority_waiters = 0
        self._low_priority_waiters = 0
        self._high_priority_queue = asyncio.Queue()
        self._low_priority_queue = asyncio.Queue()
        self._active_task_info: Optional[Dict[str, Any]] = None
        self._is_busy = False

    @property
    def is_busy(self) -> bool:
        return self._is_busy

    def get_queue_stats(self) -> dict:
        return {
            "high_priority_waiting": self._high_priority_waiters,
            "low_priority_waiting": self._low_priority_waiters,
            "is_busy": self._is_busy,
            "currently_executing": self._active_task_info
        }

    @asynccontextmanager
    async def schedule(self, model: str, priority: str = "high", task_name: str = "Inference"):
        priority = priority.lower() if priority else "high"
        is_high = (priority == "high")
        
        event = asyncio.Event()
        if is_high:
            self._high_priority_waiters += 1
            await self._high_priority_queue.put(event)
        else:
            self._low_priority_waiters += 1
            await self._low_priority_queue.put(event)

        self._trigger_next()

        await event.wait()
        
        # Lock acquired
        self._is_busy = True
        self._active_task_info = {
            "model": model,
            "priority": priority,
            "task": task_name,
            "started_at": int(time.time())
        }
        
        try:
            yield
        finally:
            self._is_busy = False
            self._active_task_info = None
            self._trigger_next()

    def _trigger_next(self):
        if self._is_busy:
            return

        # High priority has absolute precedence
        if not self._high_priority_queue.empty():
            event = self._high_priority_queue.get_nowait()
            self._high_priority_waiters = max(0, self._high_priority_waiters - 1)
            event.set()
        elif not self._low_priority_queue.empty():
            event = self._low_priority_queue.get_nowait()
            self._low_priority_waiters = max(0, self._low_priority_waiters - 1)
            event.set()


# Singleton instance
priority_scheduler = PriorityPreemptionScheduler()
