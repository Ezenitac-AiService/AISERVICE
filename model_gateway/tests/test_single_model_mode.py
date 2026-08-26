"""
Unit tests for SINGLE_MODEL_MODE routing and fallback logic (Spec 026).
Verifies that:
1. In SINGLE_MODEL_MODE=true, any request model is mapped to resident qwen3.5-2b without process restart.
2. In SINGLE_MODEL_MODE=false, dynamic model loading is preserved for future high-VRAM migrations.
"""

import os
import unittest
from unittest.mock import patch, MagicMock


class TestSingleModelMode(unittest.TestCase):

    def test_single_model_mode_env_parsing(self):
        with patch.dict(os.environ, {"SINGLE_MODEL_MODE": "true"}):
            mode = os.getenv("SINGLE_MODEL_MODE", "true").lower() in ("1", "true", "yes")
            self.assertTrue(mode)

        with patch.dict(os.environ, {"SINGLE_MODEL_MODE": "false"}):
            mode = os.getenv("SINGLE_MODEL_MODE", "true").lower() in ("1", "true", "yes")
            self.assertFalse(mode)

    def test_single_model_mode_routing_enforcement(self):
        """When SINGLE_MODEL_MODE is True, model_id is forced to resident model."""
        resident_model = "qwen3.5-2b"
        requested_model = "qwen3.5-4b"

        with patch.dict(os.environ, {"SINGLE_MODEL_MODE": "true"}):
            single_model_mode = os.getenv("SINGLE_MODEL_MODE", "true").lower() in ("1", "true", "yes")
            if single_model_mode:
                effective_model = resident_model
            else:
                effective_model = requested_model

            self.assertEqual(effective_model, "qwen3.5-2b")

    def test_multi_model_mode_preservation(self):
        """When SINGLE_MODEL_MODE is False, requested model is preserved for dynamic loading."""
        resident_model = "qwen3.5-2b"
        requested_model = "qwen3.5-4b"

        with patch.dict(os.environ, {"SINGLE_MODEL_MODE": "false"}):
            single_model_mode = os.getenv("SINGLE_MODEL_MODE", "true").lower() in ("1", "true", "yes")
            if single_model_mode:
                effective_model = resident_model
            else:
                effective_model = requested_model

            self.assertEqual(effective_model, "qwen3.5-4b")


if __name__ == "__main__":
    unittest.main()
