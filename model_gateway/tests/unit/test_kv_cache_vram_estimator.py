"""
Unit Tests for KV Cache Estimator and VRAM Budgeting (Spec 018 / T005).
Validates Q8_0 KV quantization calculations for 16K/12K contexts.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.core.process_manager import estimate_kv_cache_vram, ProcessManager


class TestKvCacheVramEstimator(unittest.TestCase):
    """Validates accurate estimation of KV Cache VRAM under Q8_0 and FP16."""

    def test_qwen_2b_16k_q8_0_estimation(self):
        """2B Q8_0 at 16K should estimate approximately ~192MB."""
        kv_mb = estimate_kv_cache_vram(
            n_layers=24,
            n_heads=14,
            head_dim=128,
            n_ctx=16384,
            n_head_kv=2,
            kv_quant="q8_0"
        )
        self.assertGreaterEqual(kv_mb, 150)
        self.assertLessEqual(kv_mb, 250)

    def test_qwen_4b_12k_q8_0_estimation(self):
        """4B Q8_0 at 12K should estimate approximately ~432MB."""
        kv_mb = estimate_kv_cache_vram(
            n_layers=36,
            n_heads=20,
            head_dim=128,
            n_ctx=12288,
            n_head_kv=4,
            kv_quant="q8_0"
        )
        self.assertGreaterEqual(kv_mb, 350)
        self.assertLessEqual(kv_mb, 550)

    def test_total_vram_under_budget(self):
        """Total estimated VRAM for 4B at 12K context must be <= 5,500MB."""
        pm = ProcessManager(port=8089)
        base_vram = 3297  # 4B Q4_K_M base
        kv_mb = estimate_kv_cache_vram(
            n_layers=36,
            n_heads=20,
            head_dim=128,
            n_ctx=12288,
            n_head_kv=4,
            kv_quant="q8_0"
        )
        total_vram = base_vram + kv_mb
        self.assertLessEqual(total_vram, 5500, f"Total VRAM {total_vram}MB exceeds 5500MB safe budget!")


if __name__ == "__main__":
    unittest.main()
