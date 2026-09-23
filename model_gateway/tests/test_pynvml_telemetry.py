"""
Unit test for PyNVML C-API <1ms non-blocking VRAM telemetry and zero nvidia-smi subprocess calls.
Validates:
1. PyNVML C-API VRAM telemetry latency (< 50ms, typically < 1ms)
2. ProcessManager uses PyNVML and makes ZERO subprocess.run(["nvidia-smi"]) calls
3. Qwen 3.5 hybrid DeltaNet KV cache calculation uses actual attention layers (8 for 9B, 6 for 4B)
"""

import time
import pytest
from unittest.mock import patch, MagicMock
from src.core.gpu_detector import get_nvml_vram_info, GpuDeviceInfo
from src.core.process_manager import ProcessManager


def test_nvml_telemetry_latency_and_info():
    """Verify get_nvml_vram_info returns valid VRAM info in < 50ms (steady state < 1ms)."""
    # Warm-up NVML initialization
    get_nvml_vram_info()

    start = time.perf_counter()
    info = get_nvml_vram_info()
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert isinstance(info, GpuDeviceInfo)
    assert info.total_vram_mb > 0
    assert info.free_vram_mb > 0
    assert elapsed_ms < 50.0, f"NVML latency was too high: {elapsed_ms:.2f}ms (expected < 50ms)"


def test_process_manager_zero_nvidia_smi_calls():
    """Verify ProcessManager does NOT invoke subprocess.run(['nvidia-smi', ...])."""
    pm = ProcessManager()

    with patch("subprocess.run") as mock_subproc:
        # Call verify_vram_released
        pm.verify_vram_released()
        mock_subproc.assert_not_called()

        # Call check_vram_runtime_overflow
        pm.check_vram_runtime_overflow()
        mock_subproc.assert_not_called()


def test_qwen_3_5_kv_cache_actual_attention_layers():
    """Verify Qwen 3.5 hybrid DeltaNet KV cache estimation uses 8 layers for 9B and 6 for 4B."""
    pm = ProcessManager()

    # 9B: 8 attention layers, 8 kv heads, head_dim 128, n_ctx 32768, q8_0 (1 byte)
    # 2 * 8 * 8 * 128 * 32768 * 1.0 = 536,870,912 bytes = 512 MB (or ~544MB with metadata)
    gqa_9b = pm._get_model_gqa_params("qwen3.5-9b")
    assert gqa_9b["n_layers"] == 8, f"Expected 8 attention layers for qwen3.5-9b, got {gqa_9b['n_layers']}"

    # 4B: 6 attention layers, 8 kv heads, head_dim 128, n_ctx 8192, q8_0 (1 byte)
    # 2 * 6 * 8 * 128 * 8192 * 1.0 = 100,663,296 bytes = 96 MB (or ~102MB with metadata)
    gqa_4b = pm._get_model_gqa_params("qwen3.5-4b")
    assert gqa_4b["n_layers"] == 6, f"Expected 6 attention layers for qwen3.5-4b, got {gqa_4b['n_layers']}"
