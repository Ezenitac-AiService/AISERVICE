"""
AsyncFairQueue — 가변 슬롯 GPU 추론 큐 관리 엔진 (Spec 031 & 006-model-gateway-upgrade).
Enforces:
- Isolated asyncio.BoundedSemaphore(1) per model (qwen3.5-9b synthesis, qwen3.5-4b router)
- 1:1 QueueTicket binding with model_id, slot_held, and slot_released flags
- State-independent idempotent RAII release_slot() to eliminate slot deadlock (CWE-833)
- Language-aware pre-queue fast DoS rejection (HTTP 400: 9B >262K chars, 4B >65K chars)
- Unified cancellation response contract (QueueCancelResponse)
"""

import os
import asyncio
import json
import time
import uuid
from typing import Optional, Dict, Any, AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import HTTPException
from .queue_models import QueueTicket, QueueStateEnum, TenantProfile, compute_prompt_hash, TicketStatus


class PreQueuePromptLimitError(HTTPException, ValueError):
    """Exception combining HTTPException and ValueError for prompt length limits."""
    def __init__(self, message: str, status_code: int = 400):
        HTTPException.__init__(
            self,
            status_code=status_code,
            detail={
                "error": {
                    "message": message,
                    "type": "invalid_request_error",
                    "param": "prompt",
                    "code": "prompt_length_exceeded",
                }
            }
        )
        ValueError.__init__(self, message)


def validate_pre_queue_prompt_limits(model_id: str = "", prompt: str = "") -> bool:
    """Pre-queue fast DoS rejection (FR-059). 4B: 65,536 chars, 9B: 262,144 chars, BGE: 6,000 chars."""
    if not prompt:
        return True
    model_lower = (model_id or "").lower()
    char_len = len(prompt)

    if "bge" in model_lower or "rerank" in model_lower or "embedding" in model_lower:
        max_chars = 6000
        max_tokens = 2048
    elif "4b" in model_lower or "fast" in model_lower or "router" in model_lower:
        max_chars = 65536
        max_tokens = 8192
    else:  # 9B or default
        max_chars = 262144
        max_tokens = 32768

    if char_len > max_chars:
        raise PreQueuePromptLimitError(
            f"Prompt character length ({char_len}) exceeds maximum pre-queue limit of {max_chars:,} characters (~{max_tokens} tokens) for model '{model_id}'."
        )
    return True


async def try_acquire_slot_nonblocking(sem: asyncio.BoundedSemaphore) -> bool:
    """FR-008: Atomic non-blocking slot acquisition strictly avoiding asyncio.wait_for timeout=0."""
    if not sem.locked():
        await sem.acquire()
        return True
    return False


def format_queue_status_event(
    position: int = 0,
    wait_sec: float = 0.0,
    custom_event: bool = False,
    data: Optional[Dict[str, Any]] = None,
) -> str:
    """Format queue progress event adhering to OpenAI SDK SSE compatibility or custom event."""
    if data is None:
        data = {"position": position, "estimated_wait_seconds": round(float(wait_sec), 2)}
    elif "position" not in data or "estimated_wait_seconds" not in data:
        data = dict(data)
        if "position" not in data:
            data["position"] = position
        if "estimated_wait_seconds" not in data:
            data["estimated_wait_seconds"] = round(float(wait_sec), 2)
    payload = json.dumps(data, ensure_ascii=False)
    if custom_event:
        return f"event: queue_status\ndata: {payload}\n\n"
    return f": queue_status {payload}\n\n"


class AsyncFairQueue:
    """가변 슬롯 비동기 공정 큐 엔진 (FR-067, FR-074)."""

    def __init__(self):
        # Per-model isolated BoundedSemaphore(1)
        self._semaphores: Dict[str, asyncio.BoundedSemaphore] = {
            "qwen3.5-9b": asyncio.BoundedSemaphore(1),
            "qwen3.5-4b": asyncio.BoundedSemaphore(1),
        }
        self._default_semaphore = asyncio.BoundedSemaphore(1)
        self._queue_capacity = int(os.getenv("QUEUE_CAPACITY", "30"))
        self._heartbeat_interval = float(os.getenv("HEARTBEAT_INTERVAL_S", "15"))

        # 전역 큐 상태
        self._tickets: Dict[str, QueueTicket] = {}
        self._queue_order: list = []  # ticket_id 순서 리스트
        self._lock = asyncio.Lock()

        # 테넌트 프로필 (DRR 공정 큐잉)
        self._tenants: Dict[str, TenantProfile] = {}

        # Request Coalescing: (session_id, prompt_hash) -> ticket_id
        self._coalescing_map: Dict[str, str] = {}
        self._coalescing_window_s = float(os.getenv("COALESCING_WINDOW_S", "5.0"))

        # 활성 슬롯 카운터
        self._active_count = 0

    @property
    def max_slots(self) -> int:
        return 1

    @property
    def active_count(self) -> int:
        return self._active_count

    @property
    def total_queued(self) -> int:
        return len(self._queue_order)

    @property
    def queue_capacity(self) -> int:
        return self._queue_capacity

    def _get_semaphore(self, model_id: str) -> asyncio.BoundedSemaphore:
        """Resolve isolated semaphore based on model ID."""
        mid = (model_id or "").lower()
        if "4b" in mid or "fast" in mid or "router" in mid:
            return self._semaphores["qwen3.5-4b"]
        elif "9b" in mid or "synthesis" in mid or "default" in mid:
            return self._semaphores["qwen3.5-9b"]
        if mid not in self._semaphores:
            self._semaphores[mid] = asyncio.BoundedSemaphore(1)
        return self._semaphores[mid]

    def _get_or_create_tenant(self, tenant_id: str) -> TenantProfile:
        """테넌트 프로필 Lazy 생성."""
        if tenant_id not in self._tenants:
            self._tenants[tenant_id] = TenantProfile(tenant_id=tenant_id)
        return self._tenants[tenant_id]

    def _compute_coalescing_key(self, session_id: str, prompt_hash: str) -> str:
        return f"{session_id}:{prompt_hash}"

    async def enqueue(
        self,
        model_id: str = "qwen3.5-9b",
        tenant_id: str = "default",
        session_id: str = "",
        prompt_hash: str = "",
        messages: Optional[list] = None,
    ) -> QueueTicket:
        """1:1 QueueTicket을 발급하고 큐에 등록."""
        if not prompt_hash and messages:
            prompt_hash = compute_prompt_hash(messages)

        async with self._lock:
            if len(self._queue_order) >= self._queue_capacity:
                raise QueueFullError(
                    f"큐 용량 초과 (현재 {len(self._queue_order)}/{self._queue_capacity}건). "
                    f"잠시 후 다시 시도해 주세요."
                )

            ticket_id = f"req_{uuid.uuid4().hex[:8]}"
            ticket = QueueTicket(
                ticket_id=ticket_id,
                tenant_id=tenant_id,
                session_id=session_id,
                prompt_hash=prompt_hash,
                created_at=time.time(),
                model_id=model_id,
                slot_held=False,
                slot_released=False,
                state=QueueStateEnum.QUEUED,
            )

            tenant = self._get_or_create_tenant(tenant_id)
            await tenant.queue.put(ticket_id)

            self._tickets[ticket_id] = ticket
            self._queue_order.append(ticket_id)

            self._recalculate_positions()

        return ticket

    async def create_fast_path_ticket(
        self,
        model_id: str = "qwen3.5-9b",
        tenant_id: str = "default",
        session_id: str = "",
        prompt_hash: str = "",
    ) -> QueueTicket:
        """T018: Create an active ticket for Zero-Wait Fast-Path when slot was already acquired non-blocking."""
        ticket_id = f"fast_{uuid.uuid4().hex[:8]}"
        ticket = QueueTicket(
            ticket_id=ticket_id,
            tenant_id=tenant_id,
            session_id=session_id,
            prompt_hash=prompt_hash,
            created_at=time.time(),
            model_id=model_id,
            slot_held=True,
            slot_released=False,
            state=QueueStateEnum.ACTIVE,
            queue_position=0,
        )
        async with self._lock:
            self._tickets[ticket_id] = ticket
            self._active_count += 1
            tenant = self._get_or_create_tenant(tenant_id)
            tenant.active_requests += 1
        return ticket

    def _recalculate_positions(self):
        """모든 대기 티켓의 순번을 재계산 (lock 내부에서 호출)."""
        pos = 1
        for tid in self._queue_order:
            t = self._tickets.get(tid)
            if t and t.state == QueueStateEnum.QUEUED:
                t.queue_position = pos
                t.estimated_wait_s = pos * 4.0
                pos += 1

    async def acquire_slot(self, ticket: QueueTicket) -> bool:
        """GPU 슬롯 획득 (모델별 격리 세마포어)."""
        sem = self._get_semaphore(ticket.model_id)
        acquire_task = asyncio.create_task(sem.acquire())
        cancel_task = asyncio.create_task(ticket.cancel_event.wait())

        done, pending = await asyncio.wait(
            {acquire_task, cancel_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        for p in pending:
            p.cancel()
            try:
                await p
            except asyncio.CancelledError:
                pass

        if cancel_task in done:
            if acquire_task in done:
                sem.release()
            return False

        async with self._lock:
            ticket.slot_held = True
            ticket.slot_released = False
            ticket.state = QueueStateEnum.ACTIVE
            ticket.queue_position = 0
            self._active_count += 1
            if ticket.ticket_id in self._queue_order:
                self._queue_order.remove(ticket.ticket_id)
            self._recalculate_positions()
            tenant = self._get_or_create_tenant(ticket.tenant_id)
            tenant.active_requests += 1

        return True

    async def release_slot(self, ticket: QueueTicket):
        """Idempotent RAII slot release (FR-067, FR-074, CWE-833)."""
        async with self._lock:
            if not ticket.slot_held or ticket.slot_released:
                return  # Idempotent: already released or never held

            ticket.slot_released = True
            ticket.slot_held = False
            if ticket.state == QueueStateEnum.ACTIVE:
                ticket.state = QueueStateEnum.COMPLETED

            self._active_count = max(0, self._active_count - 1)
            self._tickets.pop(ticket.ticket_id, None)

            key = self._compute_coalescing_key(ticket.session_id, ticket.prompt_hash)
            self._coalescing_map.pop(key, None)

            tenant = self._get_or_create_tenant(ticket.tenant_id)
            tenant.active_requests = max(0, tenant.active_requests - 1)
            self._recalculate_positions()

        sem = self._get_semaphore(ticket.model_id)
        try:
            sem.release()
        except ValueError:
            pass

    async def cancel(self, ticket_id: str) -> Dict[str, Any]:
        """Unified cancellation response protocol matching queue_management.json contract."""
        async with self._lock:
            ticket = self._tickets.get(ticket_id)
            if not ticket:
                return {
                    "ticket_id": ticket_id,
                    "status": "NOT_FOUND",
                    "previous_status": "NOT_FOUND",
                    "success": False,
                    "slot_released": False,
                    "message": f"Ticket {ticket_id} not found."
                }

            prev_status = ticket.state.value
            ticket.state = QueueStateEnum.CANCELLED
            ticket.cancel_event.set()
            was_held = ticket.slot_held and not ticket.slot_released
            if ticket_id in self._queue_order:
                self._queue_order.remove(ticket_id)
            self._tickets.pop(ticket_id, None)
            self._recalculate_positions()

        if was_held:
            await self.release_slot(ticket)

        return {
            "ticket_id": ticket_id,
            "status": "CANCELLED",
            "previous_status": prev_status,
            "success": True,
            "slot_released": ticket.slot_released,
            "message": "Ticket cancelled successfully."
        }

    async def cancel_ticket(self, ticket_id: str) -> bool:
        """Legacy bool cancel interface."""
        res = await self.cancel(ticket_id)
        return res["success"]

    async def disconnect_ticket(self, ticket_id: str):
        """클라이언트 연결 끊김 시 자동 Purge."""
        async with self._lock:
            ticket = self._tickets.get(ticket_id)
            if not ticket:
                return
            if ticket.state in (QueueStateEnum.QUEUED, QueueStateEnum.ACTIVE):
                ticket.state = QueueStateEnum.DISCONNECTED
                ticket.cancel_event.set()
                if ticket.ticket_id in self._queue_order:
                    self._queue_order.remove(ticket.ticket_id)
                self._tickets.pop(ticket_id, None)

                key = self._compute_coalescing_key(ticket.session_id, ticket.prompt_hash)
                self._coalescing_map.pop(key, None)

                self._recalculate_positions()

    async def stream_queue_events(
        self,
        ticket: QueueTicket,
        custom_event: bool = False,
    ) -> AsyncGenerator[str, None]:
        """SSE queue event stream adhering to OpenAI SDK SSE format or custom event."""
        last_position = ticket.queue_position
        last_heartbeat = time.time()
        last_status_time = time.time()
        status_interval = 3.0

        status_data = ticket.to_status_dict(
            total_queued=self.total_queued,
            active_slots=self._active_count,
            max_slots=self.max_slots,
        )
        yield format_queue_status_event(
            position=ticket.queue_position,
            wait_sec=ticket.estimated_wait_sec,
            custom_event=custom_event,
            data=status_data,
        )

        while ticket.state == QueueStateEnum.QUEUED:
            now = time.time()

            if ticket.queue_position != last_position:
                last_position = ticket.queue_position
                status_data = ticket.to_status_dict(
                    total_queued=self.total_queued,
                    active_slots=self._active_count,
                    max_slots=self.max_slots,
                )
                yield format_queue_status_event(
                    position=ticket.queue_position,
                    wait_sec=ticket.estimated_wait_sec,
                    custom_event=custom_event,
                    data=status_data,
                )
                last_status_time = now
            elif now - last_status_time >= status_interval:
                status_data = ticket.to_status_dict(
                    total_queued=self.total_queued,
                    active_slots=self._active_count,
                    max_slots=self.max_slots,
                )
                yield format_queue_status_event(
                    position=ticket.queue_position,
                    wait_sec=ticket.estimated_wait_sec,
                    custom_event=custom_event,
                    data=status_data,
                )
                last_status_time = now

            if now - last_heartbeat >= self._heartbeat_interval:
                yield ": keepalive\n\n"
                last_heartbeat = now

            if ticket.cancel_event.is_set():
                break

            await asyncio.sleep(0.5)

        if ticket.state == QueueStateEnum.ACTIVE:
            status_data = ticket.to_status_dict(
                total_queued=self.total_queued,
                active_slots=self._active_count,
                max_slots=self.max_slots,
            )
            yield format_queue_status_event(
                position=ticket.queue_position,
                wait_sec=ticket.estimated_wait_sec,
                custom_event=custom_event,
                data=status_data,
            )

    def get_stats(self) -> Dict[str, Any]:
        """큐 전체 통계 조회."""
        return {
            "active_slots": self._active_count,
            "max_slots": self.max_slots,
            "total_queued": len(self._queue_order),
            "queue_capacity": self._queue_capacity,
            "tenants": {
                tid: {
                    "active": t.active_requests,
                    "queued": t.pending_count,
                    "deficit": t.deficit_counter,
                }
                for tid, t in self._tenants.items()
            },
        }


class QueueFullError(Exception):
    """큐 용량 초과 에러."""
    pass


gpu_queue = AsyncFairQueue()
