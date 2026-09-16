import pytest
import asyncio
import os
from unittest.mock import patch
from src.core.process_manager import ProcessManager, ProcessStatusEnum, ProcessState
from src.core.llama_manager import LlamaManager
from src.core.config_manager import ConfigManager

def test_qwen35_hardware_limits():
    """T007: Test Qwen3.5 hardware limits and presets registration."""
    pm = ProcessManager(port=8089)
    assert pm.get_vram_limit("qwen3.5-2b") == 131072
    assert pm.get_vram_limit("qwen3.5-4b") == 49152
    assert pm.get_vram_limit("qwen3.5-9b") == 32768
    assert "qwen3.5-2b" in pm.model_presets

@pytest.mark.asyncio
async def test_qwen35_dry_run_vram_estimation():
    """T013 / FR-010: Test Dry-run VRAM estimation and CUDA OOM risk detection."""
    def fake_getsize(path):
        if "9b" in str(path).lower():
            return 5500 * 1024 * 1024
        return 2500 * 1024 * 1024

    pm = ProcessManager(port=8089)
    with patch("os.path.exists", return_value=True), patch("os.path.getsize", side_effect=fake_getsize):
        vram_2b = pm.estimate_vram_usage("qwen3.5-2b", 4096)
        vram_9b_large_ctx = pm.estimate_vram_usage("qwen3.5-9b", 131072)

        assert vram_2b <= 4000
        assert vram_9b_large_ctx > pm.vram_total  # Exceeds limit

        # Spawning process with excessive VRAM estimation should return ERROR state gracefully
        state = await pm.spawn_process("qwen3.5-9b", 131072)
        assert state.status == ProcessStatusEnum.ERROR
        assert "CUDA OOM Risk" in (state.error_message or "")

@pytest.mark.asyncio
async def test_qwen35_missing_model_file():
    """T013: Test error handling for missing GGUF model files."""
    pm = ProcessManager(port=8089)
    with patch("os.path.exists", return_value=False):
        state = await pm.spawn_process("qwen3.5-2b", 4096)
        assert state.status == ProcessStatusEnum.ERROR
        assert "not found" in (state.error_message or "").lower() or "Model file" in (state.error_message or "")
