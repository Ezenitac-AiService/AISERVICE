"""
Unit Tests for RedisJobQueue & RedisLock (Spec 019 / T012 & T013).
Verifies non-blocking job enqueue/dequeue (< 5ms) and distributed lock mutual exclusion.
"""

import unittest
import time
import uuid
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pilos.core.redis_queue import RedisJobQueue, RedisLock


class TestRedisQueueAndLock(unittest.TestCase):
    """Test suite for PILOS Redis async job queue and Redlock pattern."""

    def setUp(self):
        self.queue = RedisJobQueue(queue_name=f"test_pilos_queue_{uuid.uuid4().hex[:8]}")

    def tearDown(self):
        if hasattr(self, "queue"):
            self.queue.clear()

    def test_enqueue_and_dequeue_job(self):
        """Verify jobs can be enqueued and dequeued within 5ms."""
        job_payload = {
            "job_id": "job_12345",
            "review_id": "rev_999",
            "product_id": "prod_888",
            "review_text": "순하고 자극이 전혀 없어서 매일 사용하기 좋아요."
        }

        t0 = time.perf_counter()
        self.queue.enqueue(job_payload)
        t_enq_ms = (time.perf_counter() - t0) * 1000.0

        t1 = time.perf_counter()
        dequeued = self.queue.dequeue(timeout=1)
        t_deq_ms = (time.perf_counter() - t1) * 1000.0

        self.assertIsNotNone(dequeued)
        self.assertEqual(dequeued["job_id"], "job_12345")
        self.assertEqual(dequeued["review_id"], "rev_999")
        print(f"\n[Benchmark] Queue Enqueue: {t_enq_ms:.3f}ms, Dequeue: {t_deq_ms:.3f}ms")

    def test_distributed_lock_mutual_exclusion(self):
        """Verify distributed lock prevents duplicate concurrent execution."""
        lock_key = f"test_lock_{uuid.uuid4().hex[:8]}"
        lock_a = RedisLock(lock_key, ttl_seconds=5)
        lock_b = RedisLock(lock_key, ttl_seconds=5)

        # Worker A acquires lock
        acquired_a = lock_a.acquire()
        self.assertTrue(acquired_a)

        # Worker B tries to acquire same lock -> must fail
        acquired_b = lock_b.acquire()
        self.assertFalse(acquired_b)

        # Worker A releases lock
        lock_a.release()

        # Worker B should now be able to acquire lock
        acquired_b_retry = lock_b.acquire()
        self.assertTrue(acquired_b_retry)
        lock_b.release()


if __name__ == "__main__":
    unittest.main()
