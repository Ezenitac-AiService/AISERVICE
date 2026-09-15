"""
Unit Tests for ChatB RAG API Configuration & Endpoints (Spec 005 / US2).
Verifies that CoreSettings contains feature_langgraph_rag and that model-gateway
endpoints resolve without AttributeError.
"""

import unittest
import sys
import os

CHATB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if CHATB_DIR not in sys.path:
    sys.path.insert(0, CHATB_DIR)

from oliview_core.config import get_settings, CoreSettings


class TestChatBConfig(unittest.TestCase):
    def test_feature_langgraph_rag_enabled_by_default(self):
        """FR-003: CoreSettings must define feature_langgraph_rag = True by default."""
        settings = get_settings()
        self.assertTrue(hasattr(settings, "feature_langgraph_rag"), "feature_langgraph_rag missing from CoreSettings")
        self.assertIsInstance(settings.feature_langgraph_rag, bool)

    def test_endpoint_properties_available(self):
        """Verify model-gateway endpoints are accessible on settings."""
        settings = get_settings()
        self.assertTrue(hasattr(settings, "llm_endpoint"))
        self.assertTrue(hasattr(settings, "embed_endpoint"))
        self.assertTrue(hasattr(settings, "rerank_endpoint"))
        self.assertIn("v1", settings.llm_endpoint)

    def test_pipeline_timeouts_defined(self):
        """Verify pipeline timeout safety budgets."""
        settings = get_settings()
        self.assertGreaterEqual(settings.timeout_llm_sec, 60.0)
        self.assertGreaterEqual(settings.inactivity_timeout_s, 60.0)


if __name__ == "__main__":
    unittest.main()
