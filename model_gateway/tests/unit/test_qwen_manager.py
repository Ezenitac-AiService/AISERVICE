import pytest
import asyncio
import os
from src.core.process_manager import ProcessManager, ProcessStatusEnum, ProcessState
from src.core.llama_manager import LlamaManager
from src.core.config_manager import ConfigManager

def test_qwen35_hardware_limits():
    """T007: Test Qwen3.5 hardware limits and presets registration."""
    pm = ProcessManager(port=8089)
    assert pm.get_vram_limit("qwen3.5-2b") == 32000
    assert pm.get_vram_limit("qwen3.5-4b") == 18000
    assert pm.get_vram_limit("qwen3.5-9b") == 8500
    assert "qwen3.5-2b" in pm.model_presets

@pytest.mark.asyncio
async def test_qwen35_dry_run_vram_estimation():
    """T013 / FR-010: Test Dry-run VRAM estimation and CUDA OOM risk detection."""
    pm = ProcessManager(port=8089)
    with patch("os.path.exists", return_value=True), patch("os.path.getsize", return_value=2500 * 1024 * 1024):
        vram_2b = pm.estimate_vram_usage("qwen3.5-2b", 4096)
    vram_9b_large_ctx = pm.estimate_vram_usage("qwen3.5-9b", 65536)

    assert vram_2b <= 4000
    assert vram_9b_large_ctx > 11264  # Exceeds 11GB limit

    # Spawning process with excessive VRAM estimation should return ERROR state gracefully
    state = await pm.spawn_process("qwen3.5-9b", 65536)
    assert state.status == ProcessStatusEnum.ERROR
    assert "CUDA OOM Risk" in (state.error_message or "")

from unittest.mock import patch

@pytest.mark.asyncio
async def test_qwen35_missing_model_file():
    """T013: Test error handling for missing GGUF model files."""
    pm = ProcessManager(port=8089)
    with patch("os.path.exists", return_value=False):
        state = await pm.spawn_process("qwen3.5-2b", 4096)
        assert state.status == ProcessStatusEnum.ERROR
        assert "not found" in (state.error_message or "").lower() or "Model file" in (state.error_message or "")
