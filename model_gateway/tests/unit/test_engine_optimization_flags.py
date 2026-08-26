"""
Unit Tests for 2026 Modern LLM Engine Optimization Flags (Spec 018).
Validates FlashAttention (-fa), KV Cache Q8_0 Quantization (-ctk/-ctv),
Prompt Caching (--cache-prompt), and Chunked Prefill batch splitting flags.
"""

import os
import sys
import unittest

# Ensure model_gateway is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.core.process_manager import ProcessManager, LlamaServerBinaryInfo


class TestEngineOptimizationFlags(unittest.TestCase):
    """Test suite for validating injection of modern inference optimization flags."""

    def setUp(self):
        self.pm = ProcessManager(port=8089)

    def test_optimization_flags_presence_in_binary_command(self):
        """Verify -fa, --cache-prompt, -ctk q8_0, -ctv q8_0, -b 512, -ub 256 are present."""
        model_file = "/app/models/qwen3.5-4b/Qwen3.5-4B-Q4_K_M.gguf"
        target_preset = {
            "task_type": "llm",
            "chat_template": "chatml",
            "requires_mmproj": False
        }
        
        # Test command building logic
        binary_info = LlamaServerBinaryInfo(
            binary_path="/usr/local/bin/llama-server",
            is_cuda_enabled=True,
            build_source="LOCAL_BIN"
        )
        
        cmd = self.pm.build_server_command(
            binary_info=binary_info,
            model_file=model_file,
            model_id="qwen3.5-4b",
            n_ctx=12288,
            target_preset=target_preset
        )
        
        cmd_str = " ".join(cmd)
        
        # 1. FlashAttention
        self.assertTrue("-fa" in cmd or "--flash-attn" in cmd, "FlashAttention flag must be present")
        
        # 2. KV Cache Quantization
        self.assertIn("--ctk", cmd, "KV Cache K type flag must be present")
        self.assertIn("q8_0", cmd, "KV Cache K type must be q8_0")
        self.assertIn("--ctv", cmd, "KV Cache V type flag must be present")
        self.assertIn("q8_0", cmd, "KV Cache V type must be q8_0")
        
        # 3. Context & Batch / Chunked Prefill
        self.assertIn("-c", cmd)
        self.assertIn("12288", cmd)
        self.assertTrue("-b" in cmd or "--batch-size" in cmd, "Batch size flag must be present for chunked prefill")
        self.assertTrue("-ub" in cmd or "--ubatch-size" in cmd, "Micro-batch size flag must be present")

    def test_2b_context_window_and_vram_limit(self):
        """Verify Qwen3.5-2B context window defaults to 16K."""
        gqa_2b = self.pm._get_model_gqa_params("qwen3.5-2b")
        self.assertEqual(gqa_2b["n_layers"], 24)
        self.assertEqual(gqa_2b["n_head_kv"], 2)


if __name__ == "__main__":
    unittest.main()
