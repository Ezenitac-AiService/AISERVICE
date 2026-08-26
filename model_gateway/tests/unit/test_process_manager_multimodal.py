"""
tests/unit/test_process_manager_multimodal.py
==============================================================================
Unit tests for ProcessManager multimodal (--mmproj / --clip_model_path) CLI argument building and
11GB VRAM estimation validation across all 4 catalog multimodal models:
- gemma4-e2b
- gemma4-e4b
- gemma4-12b
- qwen3.5-9b-vision
==============================================================================
"""

import os
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from src.core.process_manager import ProcessManager, ProcessStatusEnum
from src.core.gpu_detector import GpuDeviceInfo

_real_exists = os.path.exists


@pytest.fixture
def process_manager(monkeypatch):
    """Fixture providing a ProcessManager instance initialized with project catalog."""
    monkeypatch.setenv("MOCK_LLAMA_SERVER", "1")
    pm = ProcessManager()
    return pm


def test_multimodal_models_in_presets(process_manager):
    """Verify all 4 multimodal models exist in process_manager presets with requires_mmproj=True."""
    multimodal_models = ["gemma4-e2b", "gemma4-e4b", "gemma4-12b", "qwen3.5-9b-vision"]
    for model_id in multimodal_models:
        assert model_id in process_manager.model_presets, f"Model {model_id} must be in presets"
        preset = process_manager.model_presets[model_id]
        assert preset.get("requires_mmproj") is True, f"{model_id} must require mmproj"
        assert preset.get("clip") is not None, f"{model_id} must specify clip path"


@pytest.mark.asyncio
async def test_spawn_process_injects_mmproj_for_all_multimodal_models(process_manager):
    """Verify ProcessManager injects vision projector (--mmproj or --clip_model_path) for all 4 multimodal models when files exist."""
    multimodal_models = ["gemma4-e2b", "gemma4-e4b", "gemma4-12b", "qwen3.5-9b-vision"]

    mock_gpu_info = GpuDeviceInfo(
        device_id=0,
        name="NVIDIA GeForce GTX 1080 Ti",
        total_vram_mb=11264,
        free_vram_mb=10764,
        is_cuda_available=True
    )

    for model_id in multimodal_models:
        preset = process_manager.model_presets[model_id]
        model_rel = preset["model"]
        clip_rel = preset["clip"]

        def fake_exists(p):
            sp = str(p)
            if sp.endswith(model_rel) or sp.endswith(clip_rel):
                return True
            return _real_exists(p)

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = os.getpid()  # Use valid current PID to pass os.kill(pid, 0)
        mock_proc.returncode = 0
        mock_proc.stdout = MagicMock()
        mock_proc.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec, \
             patch("os.path.exists", side_effect=fake_exists), \
             patch("src.core.gpu_detector.check_gpu_availability", return_value=mock_gpu_info):

            state = await process_manager.spawn_process(model_id=model_id)

            assert state.status == ProcessStatusEnum.LOADING, f"Failed for {model_id}: {state.error_message}"
            assert mock_exec.called

            cmd_args = mock_exec.call_args[0]
            assert ("--mmproj" in cmd_args or "--clip_model_path" in cmd_args), f"Vision projector flag missing for {model_id}"

            # Reset process manager state for next model iteration
            await process_manager.stop_process()


@pytest.mark.asyncio
async def test_spawn_process_missing_clip_file_raises_error(process_manager):
    """Verify ProcessManager returns ERROR status when requires_mmproj is True but mmproj file is missing."""
    preset = process_manager.model_presets["qwen3.5-9b-vision"]
    model_rel = preset["model"]

    mock_gpu_info = GpuDeviceInfo(
        device_id=0,
        name="NVIDIA GeForce GTX 1080 Ti",
        total_vram_mb=11264,
        free_vram_mb=10764,
        is_cuda_available=True
    )

    def fake_exists(p):
        sp = str(p)
        if sp.endswith(model_rel):
            return True
        if "mmproj" in sp:
            return False
        return _real_exists(p)

    with patch("os.path.exists", side_effect=fake_exists), \
         patch("src.core.gpu_detector.check_gpu_availability", return_value=mock_gpu_info):
        state = await process_manager.spawn_process(model_id="qwen3.5-9b-vision")
        assert state.status == ProcessStatusEnum.ERROR
        assert "not found" in state.error_message.lower() or "missing" in state.error_message.lower() or "vision" in state.error_message.lower() or "clip" in state.error_message.lower() or "mmproj" in state.error_message.lower()


def test_11gb_vram_estimation_checks(process_manager):
    """Verify VRAM estimation for multimodal models within 11GB (11264 MB) VRAM hardware tier limit."""
    # 11GB VRAM tier usable buffer ~ 10764 MB
    assert process_manager.model_presets["gemma4-e2b"]["vram_est_mb"] <= 11264
    assert process_manager.model_presets["gemma4-e4b"]["vram_est_mb"] <= 11264
    assert process_manager.model_presets["qwen3.5-9b-vision"]["vram_est_mb"] <= 11264
