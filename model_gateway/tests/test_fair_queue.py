"""
Unit tests for AsyncFairQueue and Queue Models (Spec 031 T006).
Slot acquisition, release, DRR fair scheduling, and capacity guards.
"""

import asyncio
import pytest
from src.core.queue_models import QueueTicket, QueueStateEnum, TenantProfile, compute_prompt_hash
from src.core.queue_manager import AsyncFairQueue, QueueFullError


def test_queue_models_prompt_hash():
    msgs1 = [{"role": "user", "content": "차앤박 프로폴리스 앰플"}]
    msgs2 = [{"role": "user", "content": "차앤박 프로폴리스 앰플"}]
    msgs3 = [{"role": "user", "content": "헤라 블랙쿠션"}]
    
    h1 = compute_prompt_hash(msgs1)
    h2 = compute_prompt_hash(msgs2)
    h3 = compute_prompt_hash(msgs3)
    
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 16


def test_async_fair_queue_enqueue_and_positions():
    async def _run():
        queue = AsyncFairQueue()
        queue._queue_capacity = 5
        
        t1 = await queue.enqueue(tenant_id="chata", session_id="s1", messages=[{"role": "user", "content": "q1"}])
        t2 = await queue.enqueue(tenant_id="chatb", session_id="s2", messages=[{"role": "user", "content": "q2"}])
        t3 = await queue.enqueue(tenant_id="chata", session_id="s3", messages=[{"role": "user", "content": "q3"}])
        
        assert t1.queue_position == 1
        assert t2.queue_position == 2
        assert t3.queue_position == 3
        assert queue.total_queued == 3
    
    asyncio.run(_run())


def test_async_fair_queue_capacity_guard():
    async def _run():
        queue = AsyncFairQueue()
        queue._queue_capacity = 2
        
        await queue.enqueue(tenant_id="chata", session_id="s1", messages=[{"role": "user", "content": "q1"}])
        await queue.enqueue(tenant_id="chatb", session_id="s2", messages=[{"role": "user", "content": "q2"}])
        
        with pytest.raises(QueueFullError):
            await queue.enqueue(tenant_id="chata", session_id="s3", messages=[{"role": "user", "content": "q3"}])
    
    asyncio.run(_run())


def test_async_fair_queue_request_coalescing():
    async def _run():
        queue = AsyncFairQueue()
        msgs = [{"role": "user", "content": "동일 질의 중복 테스트"}]
        
        t1 = await queue.enqueue(tenant_id="chata", session_id="ses_abc", messages=msgs)
        # 동일 세션 + 동일 메시지 즉시 재인입
        t2 = await queue.enqueue(tenant_id="chata", session_id="ses_abc", messages=msgs)
        
        assert t1.ticket_id == t2.ticket_id
        assert t1.subscriber_count == 2
        assert queue.total_queued == 1
    
    asyncio.run(_run())


def test_async_fair_queue_slot_acquire_and_release():
    async def _run():
        queue = AsyncFairQueue()
        queue._max_slots = 1
        queue._semaphore = asyncio.Semaphore(1)
        
        t1 = await queue.enqueue(tenant_id="chata", session_id="s1", messages=[{"role": "user", "content": "q1"}])
        t2 = await queue.enqueue(tenant_id="chatb", session_id="s2", messages=[{"role": "user", "content": "q2"}])
        
        # t1 슬롯 획득
        acquired1 = await queue.acquire_slot(t1)
        assert acquired1 is True
        assert t1.state == QueueStateEnum.ACTIVE
        assert queue.active_count == 1
        assert t2.queue_position == 1
        
        # t1 반환 후 t2 획득
        await queue.release_slot(t1)
        assert t1.state == QueueStateEnum.COMPLETED
        assert queue.active_count == 0
        
        acquired2 = await queue.acquire_slot(t2)
        assert acquired2 is True
        assert t2.state == QueueStateEnum.ACTIVE
        assert queue.active_count == 1
        
        await queue.release_slot(t2)
        assert queue.active_count == 0
    
    asyncio.run(_run())


def test_async_fair_queue_cancel():
    async def _run():
        queue = AsyncFairQueue()
        t1 = await queue.enqueue(tenant_id="chata", session_id="s1", messages=[{"role": "user", "content": "q1"}])
        t2 = await queue.enqueue(tenant_id="chatb", session_id="s2", messages=[{"role": "user", "content": "q2"}])
        
        assert queue.total_queued == 2
        
        # t1 취소
        cancelled = await queue.cancel_ticket(t1.ticket_id)
        assert cancelled is True
        assert queue.total_queued == 1
        assert t2.queue_position == 1
    
    asyncio.run(_run())
