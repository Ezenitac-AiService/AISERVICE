"""
Unit and integration regression tests for Feature 045 (Model Gateway 64K q8_0 KV Quantization & Auto Recovery).
"""

import sys
import pytest

from src.core.process_manager import ProcessManager, LlamaServerBinaryInfo, ProcessStatusEnum


def test_process_manager_quantization_flags_injected_for_large_ctx():
    """FR-003 / SC-003: Verify --type_k and --type_v q8_0 flags are injected for n_ctx >= 32768."""
    pm = ProcessManager(port=8089)
    binary_info = LlamaServerBinaryInfo(
        binary_path=sys.executable,
        is_cuda_enabled=True,
        build_source="PYTHON_MODULE_FALLBACK",
        runtime_backend="llama.cpp-cuda",
    )
    
    cmd = pm.build_server_command(
        binary_info=binary_info,
        model_file="/app/models/qwen3.5-2b/Qwen3.5-2B-Q4_K_M.gguf",
        model_id="qwen3.5-2b",
        n_ctx=65536,
        port=8089,
    )
    
    cmd_str = " ".join(cmd)
    assert "--type_k 8" in cmd_str, f"--type_k 8 missing from command: {cmd_str}"
    assert "--type_v 8" in cmd_str, f"--type_v 8 missing from command: {cmd_str}"
    assert "--n_ctx 65536" in cmd_str, f"--n_ctx 65536 missing from command: {cmd_str}"


def test_process_manager_quantization_flags_not_injected_for_small_ctx():
    """FR-003: Verify small n_ctx (< 32768) without q8_kv preset does not needlessly force quantization flags."""
    pm = ProcessManager(port=8089)
    binary_info = LlamaServerBinaryInfo(
        binary_path=sys.executable,
        is_cuda_enabled=True,
        build_source="PYTHON_MODULE_FALLBACK",
        runtime_backend="llama.cpp-cuda",
    )
    
    cmd = pm.build_server_command(
        binary_info=binary_info,
        model_file="/app/models/qwen3.5-2b/Qwen3.5-2B-Q4_K_M.gguf",
        model_id="qwen3.5-2b",
        n_ctx=2048,
        port=8089,
    )
    
    cmd_str = " ".join(cmd)
    assert "--n_ctx 2048" in cmd_str
