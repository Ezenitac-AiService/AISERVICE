import asyncio
import json
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from src.core.process_manager import ProcessStatusEnum

class EventPayload(BaseModel):
    status: ProcessStatusEnum = Field(..., description="서버 상태")
    model_id: Optional[str] = Field(None, description="현재 로딩된 모델 ID")
    n_ctx: Optional[int] = Field(None, description="컨텍스트 윈도우 크기")
    vram_usage_mb: Optional[int] = Field(None, description="추정 VRAM 사용량 (MB)")
    error: Optional[str] = Field(None, description="에러 메세지")

class EventBroadcaster:
    """Manages SSE subscribers, event queues, Bounded Queue backpressure, and heartbeat pings."""

    def __init__(self, queue_maxsize: int = 100):
        self._listeners: List[asyncio.Queue] = []
        self._queue_maxsize = queue_maxsize
        self._heartbeat_task: Optional[asyncio.Task] = None

    def subscribe(self, initial_event: Optional[Dict[str, Any]] = None) -> asyncio.Queue:
        """Subscribes a listener with a Bounded Queue."""
        q = asyncio.Queue(maxsize=self._queue_maxsize)
        self._listeners.append(q)
        if initial_event:
            self._put_event(q, initial_event)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Unsubscribes a listener."""
        if q in self._listeners:
            self._listeners.remove(q)

    def broadcast(self, event: Dict[str, Any]) -> None:
        """Broadcasts an event to all subscribers with Bounded Queue overflow recovery."""
        for q in list(self._listeners):
            self._put_event(q, event)

    def _put_event(self, q: asyncio.Queue, event: Dict[str, Any]) -> None:
        """Pushes an event into a queue. If full, drains stale items and injects full snapshot (FR-011)."""
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            # Drain queue to prevent memory leak
            while not q.empty():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    break
            # Force inject current full snapshot event
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def start_heartbeat(self, interval_seconds: float = 15.0) -> None:
        """Starts 15-second SSE comment ping heartbeat generator (FR-007)."""
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(interval_seconds))

    def stop_heartbeat(self) -> None:
        """Stops the heartbeat generator task."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

    async def _heartbeat_loop(self, interval_seconds: float) -> None:
        """Periodically broadcasts SSE comment ping packets."""
        try:
            while True:
                await asyncio.sleep(interval_seconds)
                ping_event = {"comment": "ping"}
                self.broadcast(ping_event)
        except asyncio.CancelledError:
            pass
