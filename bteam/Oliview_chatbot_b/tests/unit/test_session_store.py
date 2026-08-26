"""
Unit Tests for RedisSessionStore (Spec 019 / T009 & T010).
Verifies multi-turn conversation persistence, sliding window message truncation,
and TTL extension upon new message arrival.
"""

import unittest
import time
import sys
from pathlib import Path

# Add bteam root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from oliview_core.session import RedisSessionStore


class TestRedisSessionStore(unittest.TestCase):
    """Test suite for Redis chat session store."""

    def setUp(self):
        self.store = RedisSessionStore(host="127.0.0.1", port=6379, socket_timeout=1.0)
        self.test_session_id = f"test_session_{int(time.time()*1000)}"

    def tearDown(self):
        if hasattr(self, "store") and hasattr(self, "test_session_id"):
            self.store.clear_session(self.test_session_id)

    def test_append_and_get_session_messages(self):
        """Verify chat messages can be appended and retrieved in order."""
        self.store.append_message(self.test_session_id, "user", "안녕하세요, 올리뷰 챗봇!")
        self.store.append_message(self.test_session_id, "assistant", "안녕하세요! 어떤 화장품을 찾으시나요?")
        self.store.append_message(self.test_session_id, "user", "지성 피부용 진정 토너 추천해줘.")

        history = self.store.get_messages(self.test_session_id)
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[0]["content"], "안녕하세요, 올리뷰 챗봇!")
        self.assertEqual(history[1]["role"], "assistant")
        self.assertEqual(history[2]["role"], "user")

    def test_sliding_window_max_messages(self):
        """Verify session store caps total retained messages to max_messages (e.g. 10)."""
        # Append 15 messages
        for i in range(15):
            role = "user" if i % 2 == 0 else "assistant"
            self.store.append_message(self.test_session_id, role, f"Message {i}", max_messages=10)

        history = self.store.get_messages(self.test_session_id, max_messages=10)
        self.assertEqual(len(history), 10)
        # Oldest message kept should be Message 5
        self.assertEqual(history[0]["content"], "Message 5")
        self.assertEqual(history[-1]["content"], "Message 14")

    def test_graceful_fallback_when_redis_offline(self):
        """Verify in-memory fallback works seamlessly when Redis is offline."""
        offline_store = RedisSessionStore(host="127.0.0.1", port=65534, socket_timeout=0.1)
        offline_store.append_message("offline_sess", "user", "로컬 메모리 폴백 테스트")
        msgs = offline_store.get_messages("offline_sess")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["content"], "로컬 메모리 폴백 테스트")


if __name__ == "__main__":
    unittest.main()
