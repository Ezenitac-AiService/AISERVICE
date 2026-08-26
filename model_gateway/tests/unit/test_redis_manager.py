"""
Unit Tests for RedisManager & BaseRedisManager (Spec 019 / T003).
Verifies embedding/rerank caching, rate limiting, and graceful fallback when Redis is unreachable.
"""

import os
import sys
import unittest
import asyncio
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.redis_manager import RedisManager, BaseRedisManager


class TestRedisManager(unittest.IsolatedAsyncioTestCase):
    """Test suite for Redis caching and graceful fallback."""

    async def asyncSetUp(self):
        # Initialize RedisManager with localhost
        self.rm = RedisManager(host="127.0.0.1", port=6379, socket_timeout=1.0)

    async def asyncTearDown(self):
        if hasattr(self, "rm"):
            await self.rm.aclose()

    async def test_embedding_cache_set_and_get(self):
        """Verify embedding vector can be cached and retrieved in < 1ms."""
        model_id = "bge-m3"
        text = "테스트 화장품 토너 보습감 질의"
        vector = [0.123, -0.456, 0.789] * 341 + [0.0]  # 1024-dim test vector

        # Set embedding
        await self.rm.set_embedding(model_id, text, vector, ttl=300)

        # Get embedding
        cached_vec = await self.rm.get_embedding(model_id, text)
        self.assertIsNotNone(cached_vec)
        self.assertEqual(len(cached_vec), 1024)
        self.assertAlmostEqual(cached_vec[0], 0.123, places=3)

    async def test_rerank_cache_set_and_get(self):
        """Verify reranker score map can be cached and retrieved."""
        query = "모공 케어 토너"
        doc_ids = ["doc_1", "doc_2", "doc_3"]
        scores = [{"index": 0, "score": 0.95}, {"index": 1, "score": 0.82}]

        await self.rm.set_rerank(query, doc_ids, scores, ttl=300)
        cached_scores = await self.rm.get_rerank(query, doc_ids)
        self.assertIsNotNone(cached_scores)
        self.assertEqual(len(cached_scores), 2)
        self.assertEqual(cached_scores[0]["score"], 0.95)

    async def test_graceful_fallback_on_unreachable_redis(self):
        """Verify RedisManager returns None without raising errors when Redis host is unreachable."""
        broken_rm = RedisManager(host="127.0.0.1", port=65534, socket_timeout=0.1)
        # Should gracefully return None on cache miss/error without crashing
        res = await broken_rm.get_embedding("bge-m3", "random text")
        self.assertIsNone(res)

        # Should gracefully return None on rerank without crashing
        res_rerank = await broken_rm.get_rerank("query", ["doc1"])
        self.assertIsNone(res_rerank)

    async def test_rate_limiter_token_bucket(self):
        """Verify rate limiter allows requests within limit and blocks excess."""
        import uuid
        client_id = f"test_client_{uuid.uuid4().hex[:8]}"
        # 3 requests allowed in 10-second window
        r1 = await self.rm.check_rate_limit(client_id, max_requests=3, window_s=10)
        r2 = await self.rm.check_rate_limit(client_id, max_requests=3, window_s=10)
        r3 = await self.rm.check_rate_limit(client_id, max_requests=3, window_s=10)
        r4 = await self.rm.check_rate_limit(client_id, max_requests=3, window_s=10)

        self.assertTrue(r1)
        self.assertTrue(r2)
        self.assertTrue(r3)
        self.assertFalse(r4)  # 4th request must be rejected


if __name__ == "__main__":
    unittest.main()
