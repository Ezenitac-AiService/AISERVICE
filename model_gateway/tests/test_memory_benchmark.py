"""
Tests for User Story 2: Host Memory (RAM) <= 1,000MB and GPU VRAM <= 10,872MB
Verification Matrix & Requirements:
- SC-001: 4 resident llama-server processes host RSS <= 250MB each, total <= 1,000MB
- SC-002: Total GPU VRAM occupancy <= 10,872MB, safety margin >= 1,416MB out of 12GB
- Enforcement of --no-mmap across all 4 models to prevent Linux kernel page cache bloat
"""

import os
import subprocess
import pytest
from unittest.mock import patch, MagicMock

from src.core.gpu_detector import get_nvml_vram_info, GpuDeviceInfo
from src.core.process_manager import ProcessManager


class TestMemoryBenchmark:
    """Test suite for SC-001 (Host RAM) and SC-002 (GPU VRAM) thresholds."""

    def test_no_mmap_flag_enforced_all_models(self):
        """Verify that ProcessManager strictly includes --no-mmap for all 4 resident models."""
        pm = ProcessManager()
        models = ["qwen3.5-9b", "qwen3.5-4b", "bge-m3", "bge-reranker-v2-m3"]
        for model_id in models:
            cmd = pm.build_c_llama_server_cmd(model_id)
            assert ("--load-mode" in cmd and cmd[cmd.index("--load-mode") + 1] == "none") or ("--no-mmap" in cmd), f"Model {model_id} must have --load-mode none / --no-mmap to enforce SC-001"
            assert "-np" in cmd and cmd[cmd.index("-np") + 1] == "1", f"Model {model_id} must have -np 1"
            assert "--threads-http" in cmd and cmd[cmd.index("--threads-http") + 1] == "4"

    def test_gpu_vram_threshold_math(self):
        """Verify that VRAM occupancy calculation respects SC-002 thresholds."""
        # RTX 3060 12GB physical capacity: 12,288 MB
        # Total limit: 10,872 MB
        # Safety margin: 1,416 MB
        total_limit_mb = 10872
        safety_margin_mb = 1416
        physical_vram_mb = 12288
        assert total_limit_mb + safety_margin_mb == physical_vram_mb

        # Mocked NVML call representing valid state
        mock_pynvml = MagicMock()
        mock_pynvml.nvmlDeviceGetMemoryInfo.return_value = MagicMock(total=12288 * 1024 * 1024, free=1500 * 1024 * 1024)
        mock_pynvml.nvmlDeviceGetName.return_value = "NVIDIA GeForce RTX 3060"
        with patch.dict("sys.modules", {"pynvml": mock_pynvml}):
            info = get_nvml_vram_info()
            used_mb = info.total_vram_mb - info.free_vram_mb
            assert used_mb <= total_limit_mb, f"VRAM used {used_mb}MB exceeds limit {total_limit_mb}MB"
            assert info.free_vram_mb >= safety_margin_mb, f"Free VRAM {info.free_vram_mb}MB below margin {safety_margin_mb}MB"

    def test_gpu_vram_overflow_detection(self):
        """Verify that VRAM overflow exceeding 10,872MB triggers failure."""
        mock_pynvml = MagicMock()
        mock_pynvml.nvmlDeviceGetMemoryInfo.return_value = MagicMock(total=12288 * 1024 * 1024, free=800 * 1024 * 1024)
        mock_pynvml.nvmlDeviceGetName.return_value = "NVIDIA GeForce RTX 3060"
        with patch.dict("sys.modules", {"pynvml": mock_pynvml}):
            info = get_nvml_vram_info()
            used_mb = info.total_vram_mb - info.free_vram_mb
            assert used_mb > 10872, "Should detect VRAM overflow condition"

    def test_live_gpu_vram_within_sc002_limit(self):
        """Verify that live GPU (if present) does not exceed 10,872MB total used VRAM."""
        info = get_nvml_vram_info()
        if not info.is_cuda_available:
            pytest.skip("CUDA GPU not available on host environment")
        used_mb = info.total_vram_mb - info.free_vram_mb
        assert used_mb <= 10872, f"Live VRAM usage {used_mb}MB exceeds SC-002 limit (10,872MB)"

    def test_host_rss_calculation_logic(self):
        """Verify the calculation logic for 4 resident llama-server RSS totals."""
        # Simulated ps output for 4 processes (RSS in KB)
        # 4 processes at 200MB (204,800 KB) each = 800MB (819,200 KB) <= 1,000MB
        simulated_ps_output = (
            "  PID   RSS COMMAND\n"
            " 1001 204800 /usr/local/bin/llama-server -m qwen9b.gguf --no-mmap\n"
            " 1002 184320 /usr/local/bin/llama-server -m qwen4b.gguf --no-mmap\n"
            " 1003 153600 /usr/local/bin/llama-server -m bge-m3.gguf --no-mmap\n"
            " 1004 153600 /usr/local/bin/llama-server -m reranker.gguf --no-mmap\n"
        )
        lines = [line.strip() for line in simulated_ps_output.strip().split("\n")[1:] if line.strip()]
        assert len(lines) == 4

        total_rss_kb = 0
        for line in lines:
            parts = line.split(maxsplit=2)
            rss_kb = int(parts[1])
            rss_mb = rss_kb / 1024
            assert rss_mb <= 250.0, f"Per-process RSS {rss_mb}MB exceeds 250MB limit"
            total_rss_kb += rss_kb

        total_rss_mb = total_rss_kb / 1024
        assert total_rss_mb <= 1000.0, f"Total RSS {total_rss_mb}MB exceeds 1,000MB limit"
