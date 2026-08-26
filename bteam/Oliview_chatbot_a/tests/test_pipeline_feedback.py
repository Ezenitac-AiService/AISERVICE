"""Unit Tests for Real-time Pipeline Feedback & Error Boundary (Spec 037 US3)."""
import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from oliview_core.config import get_settings


class TestPipelineFeedback(unittest.TestCase):

    def test_dev_environment_lenient_timeouts(self):
        settings = get_settings()
        # 개발/실증(POC) 모드 타임아웃 검증 (Inactivity >= 45s, Total >= 180s)
        self.assertGreaterEqual(settings.inactivity_timeout_s, 45.0)
        self.assertGreaterEqual(settings.timeout_llm_sec, 180.0)
        self.assertGreaterEqual(settings.timeout_rerank_sec, 20.0)

    def test_top_p_sampling_defaults(self):
        settings = get_settings()
        self.assertEqual(settings.default_top_p, 0.85)
        self.assertEqual(settings.default_temperature, 0.3)
        self.assertEqual(settings.default_repetition_penalty, 1.05)


if __name__ == "__main__":
    unittest.main()
