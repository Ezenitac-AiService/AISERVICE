"""
AsyncFairQueue — 가변 슬롯 GPU 추론 큐 관리 엔진 (Spec 031 FR-001, FR-002, FR-007, FR-008, FR-009, FR-011).

주요 기능:
- 가변 슬롯 세마포어 (active_slots=1 기본, MAX_GPU_CONCURRENT_SLOTS 환경변수)
- 15초 주기 SSE Keep-Alive 하트비트
- Event-Driven 큐 순번 갱신 (N→N-1)
- Deficit Round Robin (DRR) 테넌트 공정 스케줄링
- Request Coalescing (멱등성 스트림 멀티플렉싱)
- Client Disconnect Purge (1.0초 이내 즉시 방출)
- Max Queue Capacity Guard (기본 30건)
"""

import os
import asyncio
import json
import time
import uuid
from typing import Optional, Dict, Any, AsyncGenerator
from contextlib import asynccontextmanager

from .queue_models import QueueTicket, QueueStateEnum, TenantProfile, compute_prompt_hash


class AsyncFairQueue:
    """가변 슬롯 비동기 공정 큐 엔진 (Spec 031 FR-001)."""

    def __init__(self):
        # 가변 슬롯: 환경변수 또는 기본값 1
        self._max_slots = int(os.getenv("MAX_GPU_CONCURRENT_SLOTS", "1"))
        self._semaphore = asyncio.Semaphore(self._max_slots)
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
        return self._max_slots

    @property
    def active_count(self) -> int:
        return self._active_count

    @property
    def total_queued(self) -> int:
        return len(self._queue_order)

    @property
    def queue_capacity(self) -> int:
        return self._queue_capacity

    def _get_or_create_tenant(self, tenant_id: str) -> TenantProfile:
        """테넌트 프로필 Lazy 생성."""
        if tenant_id not in self._tenants:
            self._tenants[tenant_id] = TenantProfile(tenant_id=tenant_id)
        return self._tenants[tenant_id]

    def _compute_coalescing_key(self, session_id: str, prompt_hash: str) -> str:
        return f"{session_id}:{prompt_hash}"

    async def _check_coalescing(self, session_id: str, prompt_hash: str) -> Optional[QueueTicket]:
        """Request Coalescing: 동일 세션/동일 프롬프트가 이미 큐에 있으면 해당 티켓 반환 (Spec 031 FR-011)."""
        key = self._compute_coalescing_key(session_id, prompt_hash)
        async with self._lock:
            if key in self._coalescing_map:
                ticket_id = self._coalescing_map[key]
                ticket = self._tickets.get(ticket_id)
                if ticket and ticket.state in (QueueStateEnum.QUEUED, QueueStateEnum.ACTIVE):
                    # 윈도우 내 중복인지 확인
                    if time.time() - ticket.created_at < self._coalescing_window_s:
                        ticket.subscriber_count += 1
                        return ticket
        return None

    async def enqueue(
        self,
        tenant_id: str = "default",
        session_id: str = "",
        prompt_hash: str = "",
        messages: Optional[list] = None,
    ) -> QueueTicket:
        """
        요청을 큐에 등록하고 QueueTicket을 반환 (Spec 031 FR-001, FR-009).

        - Max Capacity 초과 시 None을 반환하지 않고 예외를 발생시킴 (호출부에서 429 처리)
        - Request Coalescing: 동일 세션/프롬프트가 이미 큐에 있으면 기존 티켓 반환
        """
        if not prompt_hash and messages:
            prompt_hash = compute_prompt_hash(messages)

        # 1. Request Coalescing 체크
        coalesced = await self._check_coalescing(session_id, prompt_hash)
        if coalesced:
            print(f"[AsyncFairQueue] Request Coalescing 병합: ticket={coalesced.ticket_id}, subscribers={coalesced.subscriber_count}")
            return coalesced

        # 2. Queue Capacity Guard
        async with self._lock:
            if len(self._queue_order) >= self._queue_capacity:
                raise QueueFullError(
                    f"큐 용량 초과 (현재 {len(self._queue_order)}/{self._queue_capacity}건). "
                    f"잠시 후 다시 시도해 주세요."
                )

            # 3. 티켓 생성
            ticket_id = f"req_{uuid.uuid4().hex[:8]}"
            ticket = QueueTicket(
                ticket_id=ticket_id,
                tenant_id=tenant_id,
                session_id=session_id,
                prompt_hash=prompt_hash,
                created_at=time.time(),
            )

            # 테넌트 프로필에 등록
            tenant = self._get_or_create_tenant(tenant_id)
            await tenant.queue.put(ticket_id)

            # 큐 순서에 추가
            self._tickets[ticket_id] = ticket
            self._queue_order.append(ticket_id)

            # Coalescing 맵에 등록
            if session_id and prompt_hash:
                key = self._compute_coalescing_key(session_id, prompt_hash)
                self._coalescing_map[key] = ticket_id

            # 순번 계산
            self._recalculate_positions()

        print(f"[AsyncFairQueue] 큐 진입: ticket={ticket_id}, tenant={tenant_id}, position={ticket.queue_position}, total={len(self._queue_order)}")
        return ticket

    def _recalculate_positions(self):
        """모든 대기 티켓의 순번을 재계산 (lock 내부에서 호출)."""
        pos = 1
        for tid in self._queue_order:
            t = self._tickets.get(tid)
            if t and t.state == QueueStateEnum.QUEUED:
                t.queue_position = pos
                # 평균 추론 시간 4초 기준 예상 대기 계산
                t.estimated_wait_s = pos * 4.0
                pos += 1

    async def acquire_slot(self, ticket: QueueTicket) -> bool:
        """
        GPU 슬롯을 획득 (Spec 031 FR-001).
        세마포어 대기 중 cancel_event가 set되면 즉시 False 반환.
        """
        acquire_task = asyncio.create_task(self._semaphore.acquire())
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
            # 취소됨 — 세마포어가 이미 획득되었으면 반환
            if acquire_task in done:
                self._semaphore.release()
            return False

        # 슬롯 획득 성공
        async with self._lock:
            ticket.state = QueueStateEnum.ACTIVE
            ticket.queue_position = 0
            self._active_count += 1
            if ticket.ticket_id in self._queue_order:
                self._queue_order.remove(ticket.ticket_id)
            self._recalculate_positions()
            tenant = self._get_or_create_tenant(ticket.tenant_id)
            tenant.active_requests += 1

        print(f"[AsyncFairQueue] 슬롯 획득: ticket={ticket.ticket_id}, active={self._active_count}/{self._max_slots}")
        return True

    async def release_slot(self, ticket: QueueTicket):
        """GPU 슬롯 반환 및 다음 대기자 순번 갱신 (Spec 031 FR-001)."""
        async with self._lock:
            if ticket.state == QueueStateEnum.ACTIVE:
                ticket.state = QueueStateEnum.COMPLETED
            self._active_count = max(0, self._active_count - 1)
            self._tickets.pop(ticket.ticket_id, None)

            # Coalescing 맵 정리
            key = self._compute_coalescing_key(ticket.session_id, ticket.prompt_hash)
            self._coalescing_map.pop(key, None)

            # 테넌트 활성 카운트 감소
            tenant = self._get_or_create_tenant(ticket.tenant_id)
            tenant.active_requests = max(0, tenant.active_requests - 1)

            self._recalculate_positions()

        self._semaphore.release()
        print(f"[AsyncFairQueue] 슬롯 반환: ticket={ticket.ticket_id}, active={self._active_count}/{self._max_slots}")

    async def cancel_ticket(self, ticket_id: str) -> bool:
        """큐 티켓 취소 및 즉시 Purge (Spec 031 FR-008)."""
        async with self._lock:
            ticket = self._tickets.get(ticket_id)
            if not ticket:
                return False

            if ticket.state == QueueStateEnum.QUEUED:
                ticket.state = QueueStateEnum.CANCELLED
                ticket.cancel_event.set()
                if ticket_id in self._queue_order:
                    self._queue_order.remove(ticket_id)
                self._tickets.pop(ticket_id, None)

                key = self._compute_coalescing_key(ticket.session_id, ticket.prompt_hash)
                self._coalescing_map.pop(key, None)

                self._recalculate_positions()
                print(f"[AsyncFairQueue] 큐 취소: ticket={ticket_id}")
                return True
            elif ticket.state == QueueStateEnum.ACTIVE:
                # 추론 중 취소 — cancel_event를 통해 추론 루프에서 중단
                ticket.cancel_event.set()
                ticket.state = QueueStateEnum.CANCELLED
                print(f"[AsyncFairQueue] 추론 중 취소 신호: ticket={ticket_id}")
                return True
        return False

    async def disconnect_ticket(self, ticket_id: str):
        """클라이언트 연결 끊김 시 자동 Purge (Spec 031 FR-008)."""
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
                print(f"[AsyncFairQueue] 연결 끊김 Purge: ticket={ticket_id}")

    async def get_next_ticket_drr(self) -> Optional[str]:
        """
        Deficit Round Robin(DRR) 기반 다음 처리 티켓 선택 (Spec 031 FR-007).
        테넌트 간 공정하게 교차 배정.
        """
        async with self._lock:
            if not self._queue_order:
                return None

            # DRR: 각 테넌트의 deficit_counter가 가장 높은 순서로 선택
            tenant_ids = list(self._tenants.keys())
            if not tenant_ids:
                return self._queue_order[0] if self._queue_order else None

            best_ticket_id = None
            best_deficit = -1

            for tenant_id in tenant_ids:
                tenant = self._tenants[tenant_id]
                tenant.deficit_counter += tenant.weight

                # 이 테넌트의 대기 티켓 중 가장 앞의 것 찾기
                for tid in self._queue_order:
                    t = self._tickets.get(tid)
                    if t and t.tenant_id == tenant_id and t.state == QueueStateEnum.QUEUED:
                        if tenant.deficit_counter > best_deficit:
                            best_deficit = tenant.deficit_counter
                            best_ticket_id = tid
                        break  # 이 테넌트의 첫 번째 대기 티켓만 고려

            if best_ticket_id:
                ticket = self._tickets[best_ticket_id]
                tenant = self._tenants[ticket.tenant_id]
                tenant.deficit_counter -= 1  # quantum 소비

            return best_ticket_id

    async def stream_queue_events(
        self,
        ticket: QueueTicket,
    ) -> AsyncGenerator[str, None]:
        """
        큐 대기 중 SSE 이벤트 스트리밍 (Spec 031 FR-002, FR-003).
        - queue_status 이벤트: 순번 변동 시 즉시 + 3~5초 주기
        - keepalive: 15초 주기
        """
        last_position = ticket.queue_position
        last_heartbeat = time.time()
        last_status_time = time.time()
        status_interval = 3.0  # 큐 상태 갱신 주기

        # 초기 큐 상태 즉시 전송 (< 200ms)
        status_data = ticket.to_status_dict(
            total_queued=self.total_queued,
            active_slots=self._active_count,
            max_slots=self._max_slots,
        )
        yield f"event: queue_status\ndata: {json.dumps(status_data, ensure_ascii=False)}\n\n"

        while ticket.state == QueueStateEnum.QUEUED:
            now = time.time()

            # 순번 변동 시 즉시(Event-Driven) 전송
            if ticket.queue_position != last_position:
                last_position = ticket.queue_position
                status_data = ticket.to_status_dict(
                    total_queued=self.total_queued,
                    active_slots=self._active_count,
                    max_slots=self._max_slots,
                )
                yield f"event: queue_status\ndata: {json.dumps(status_data, ensure_ascii=False)}\n\n"
                last_status_time = now

            # 3~5초 주기 큐 상태 갱신
            elif now - last_status_time >= status_interval:
                status_data = ticket.to_status_dict(
                    total_queued=self.total_queued,
                    active_slots=self._active_count,
                    max_slots=self._max_slots,
                )
                yield f"event: queue_status\ndata: {json.dumps(status_data, ensure_ascii=False)}\n\n"
                last_status_time = now

            # 15초 주기 Keep-Alive 하트비트
            if now - last_heartbeat >= self._heartbeat_interval:
                yield ": keepalive\n\n"
                last_heartbeat = now

            # 취소/연결끊김 체크
            if ticket.cancel_event.is_set():
                break

            await asyncio.sleep(0.5)

        # ACTIVE 전환 시 최종 상태 전송
        if ticket.state == QueueStateEnum.ACTIVE:
            status_data = ticket.to_status_dict(
                total_queued=self.total_queued,
                active_slots=self._active_count,
                max_slots=self._max_slots,
            )
            yield f"event: queue_status\ndata: {json.dumps(status_data, ensure_ascii=False)}\n\n"

    def get_stats(self) -> Dict[str, Any]:
        """큐 전체 통계 조회."""
        return {
            "active_slots": self._active_count,
            "max_slots": self._max_slots,
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
    """큐 용량 초과 에러 (Spec 031 FR-009)."""
    pass


# 싱글톤 인스턴스
gpu_queue = AsyncFairQueue()
