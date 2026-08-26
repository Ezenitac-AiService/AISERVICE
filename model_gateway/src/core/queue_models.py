"""
Queue Data Models for GPU Inference Queue Management (Spec 031).
QueueTicket, QueueStateEnum, TenantProfile — 가변 슬롯 큐 엔진의 핵심 엔티티.
"""

import asyncio
import time
import hashlib
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


class QueueStateEnum(str, Enum):
    """큐 티켓의 라이프사이클 상태."""
    QUEUED = "QUEUED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    DISCONNECTED = "DISCONNECTED"


@dataclass
class QueueTicket:
    """큐에 진입한 개별 요청의 상태 관리 객체 (Spec 031 FR-001)."""
    ticket_id: str
    tenant_id: str
    session_id: str
    prompt_hash: str
    created_at: float
    state: QueueStateEnum = QueueStateEnum.QUEUED
    queue_position: int = 1
    estimated_wait_s: float = 0.0
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    subscriber_count: int = 1
    # 스트림 멀티플렉싱을 위한 브로드캐스트 큐 리스트
    broadcast_queues: list = field(default_factory=list)

    def to_status_dict(self, total_queued: int = 0, active_slots: int = 1, max_slots: int = 1) -> Dict[str, Any]:
        """SSE event: queue_status 페이로드 생성."""
        return {
            "ticket_id": self.ticket_id,
            "tenant_id": self.tenant_id,
            "status": self.state.value,
            "queue_position": self.queue_position,
            "total_queued": total_queued,
            "active_slots": active_slots,
            "max_slots": max_slots,
            "estimated_wait_sec": round(self.estimated_wait_s, 1),
            "elapsed_sec": round(time.time() - self.created_at, 1),
            "timestamp": time.time(),
        }


@dataclass
class TenantProfile:
    """서비스 테넌트(Chat A, Chat B 등)별 공정 큐잉 메타데이터 (Spec 031 FR-007)."""
    tenant_id: str
    weight: int = 1
    deficit_counter: int = 0
    active_requests: int = 0
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)

    @property
    def pending_count(self) -> int:
        return self.queue.qsize()


def compute_prompt_hash(messages: list) -> str:
    """요청 메시지 리스트에서 SHA256 해시를 계산하여 Request Coalescing에 사용."""
    content = ""
    for msg in messages:
        if isinstance(msg, dict):
            content += msg.get("role", "") + ":" + msg.get("content", "") + "|"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
