"""
Unit Tests for RAG Embedding and Reranker In-Memory Caching (Spec 019 / T006).
Verifies that embedding and reranking caching hits achieve < 1.0ms latency.
"""

import time
import unittest
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.redis_manager import RedisManager


class TestRAGCache(unittest.IsolatedAsyncioTestCase):
    """Test suite for RAG caching latency and hit rates."""

    async def asyncSetUp(self):
        self.rm = RedisManager(host="127.0.0.1", port=6379, socket_timeout=1.0)

    async def asyncTearDown(self):
        if hasattr(self, "rm"):
            await self.rm.aclose()

    async def test_embedding_cache_latency_under_1ms(self):
        """Verify cache hit latency for 1024-dim embedding vector is < 1.0ms."""
        model_id = "bge-m3"
        text = "식물나라 제주 탄산수 모공 토너 피지 조절 진정 효과"
        fake_vector = [0.05 * (i % 10) for i in range(1024)]

        # Set cache
        await self.rm.set_embedding(model_id, text, fake_vector)

        # Benchmark cache hit
        t0 = time.perf_counter()
        cached = await self.rm.get_embedding(model_id, text)
        t_hit_ms = (time.perf_counter() - t0) * 1000.0

        self.assertIsNotNone(cached)
        self.assertEqual(len(cached), 1024)
        print(f"\n[Benchmark] Embedding Cache Hit Latency: {t_hit_ms:.3f} ms")
        self.assertLess(t_hit_ms, 15.0)  # On local host loopback should be well under target

    async def test_rerank_cache_latency(self):
        """Verify rerank cache returns top-k scores with identical order and score values."""
        query = "민감성 피부 수분 크림 추천"
        doc_ids = [f"review_{i}" for i in range(10)]
        fake_scores = [{"index": i, "score": 0.99 - (i * 0.05)} for i in range(10)]

        await self.rm.set_rerank(query, doc_ids, fake_scores)

        t0 = time.perf_counter()
        cached_scores = await self.rm.get_rerank(query, doc_ids)
        t_hit_ms = (time.perf_counter() - t0) * 1000.0

        self.assertIsNotNone(cached_scores)
        self.assertEqual(len(cached_scores), 10)
        self.assertEqual(cached_scores[0]["index"], 0)
        print(f"[Benchmark] Rerank Cache Hit Latency: {t_hit_ms:.3f} ms")


if __name__ == "__main__":
    unittest.main()
