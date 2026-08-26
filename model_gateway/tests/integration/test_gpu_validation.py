"""
Integration tests for GPU CUDA validation, CPU fallback blocking, and VRAM offload status.
"""

import pytest
import os
from unittest.mock import patch, MagicMock
from src.core.process_manager import ProcessManager, ProcessStatusEnum
from src.core.gpu_detector import GpuAccelerationError, check_gpu_availability


@pytest.mark.asyncio
async def test_spawn_process_cpu_only_blocked():
    pm = ProcessManager(port=8081)
    os.environ["MOCK_CPU_ONLY"] = "1"
    try:
        state = await pm.spawn_process("qwen3.5-2b", 4096)
        assert state.status == ProcessStatusEnum.ERROR
        assert "GpuAccelerationError" in state.error_message
        assert "CPU-only execution is strictly blocked" in state.error_message
    finally:
        os.environ.pop("MOCK_CPU_ONLY", None)


@pytest.mark.asyncio
async def test_spawn_process_mock_llama_server_gpu_allowed():
    pm = ProcessManager(port=8081)
    os.environ["MOCK_LLAMA_SERVER"] = "1"
    try:
        state = await pm.spawn_process("qwen3.5-2b", 4096)
        assert state.status == ProcessStatusEnum.LOADING
        await pm.stop_process()
        assert pm.state.status == ProcessStatusEnum.UNLOADED
    finally:
        os.environ.pop("MOCK_LLAMA_SERVER", None)

def test_verify_vram_released_success():
    pm = ProcessManager(port=8081)
    pm.vram_total = 24000
    with patch("shutil.which", return_value="/usr/bin/nvidia-smi"):
        mock_result = MagicMock()
        mock_result.stdout = "23900\n"
        with patch("subprocess.run", return_value=mock_result):
            assert pm.verify_vram_released(baseline_free_vram_mb=24000, tolerance_mb=200) is True

def test_verify_vram_released_failure():
    pm = ProcessManager(port=8081)
    pm.vram_total = 24000
    with patch("shutil.which", return_value="/usr/bin/nvidia-smi"):
        mock_result = MagicMock()
        mock_result.stdout = "20000\n"
        with patch("subprocess.run", return_value=mock_result):
            assert pm.verify_vram_released(baseline_free_vram_mb=24000, tolerance_mb=200) is False


def test_real_mode_gpu_execution(test_mode):
    """FR-004 / FR-005: Validates test_mode fixture and real GPU execution when test_mode == 'real'."""
    pm = ProcessManager(port=8082)
    if test_mode == "real":
        gpu_info = check_gpu_availability()
        assert gpu_info.is_cuda_available is True
    else:
        assert test_mode == "mock"


def test_verify_vram_released_nvidia_smi_missing():
    pm = ProcessManager(port=8081)
    with patch("shutil.which", return_value=None):
        assert pm.verify_vram_released(baseline_free_vram_mb=24000) is True


@pytest.mark.asyncio
async def test_graceful_stream_drain_and_port_release():
    """T009: Graceful Stream Drain active_requests wait and port release verification."""
    pm = ProcessManager(port=8081)
    os.environ["MOCK_LLAMA_SERVER"] = "1"
    try:
        await pm.spawn_process("qwen3.5-2b", 4096)
        pm.state = pm.state.model_copy(update={"active_requests": 1})
        assert pm.state.active_requests == 1
        
        # In background, decrement active_requests to simulate stream completion
        async def mock_stream_drain():
            await asyncio.sleep(0.4)
            pm.state = pm.state.model_copy(update={"active_requests": 0})
            
        import asyncio
        asyncio.create_task(mock_stream_drain())
        
        # stop_process should drain active_requests, terminate process, and clear port
        state = await pm.stop_process()
        assert state.status == ProcessStatusEnum.UNLOADED
        assert pm.state.active_requests == 0
    finally:
        os.environ.pop("MOCK_LLAMA_SERVER", None)


# T011 / US3: Integration test for VRAM offload and process PID detection (FR-004)

def test_validate_cuda_build_environment_integration():
    """T011: validate_cuda_build_environment()가 현재 환경에서 GPU를 정상 감지해야 한다."""
    from src.core.gpu_detector import validate_cuda_build_environment
    # Should succeed on NVIDIA GPU systems (this is an integration test)
    assert validate_cuda_build_environment() is True


def test_nvidia_smi_vram_and_pid_detection():
    """T011: nvidia-smi로 GPU VRAM 사용량 및 프로세스 PID를 조회할 수 있어야 한다."""
    import shutil
    import subprocess

    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        pytest.skip("nvidia-smi not available")

    # Test GPU memory query
    result = subprocess.run(
        [nvidia_smi, "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True
    )
    parts = [p.strip() for p in result.stdout.strip().split(",")]
    assert len(parts) >= 3, f"Expected 3 fields from nvidia-smi, got: {parts}"
    gpu_name = parts[0]
    used_mb = int(parts[1])
    total_mb = int(parts[2])
    assert total_mb > 0, "GPU total VRAM must be positive"
    assert gpu_name, "GPU name must not be empty"

    # Test GPU process query (just verify the command works)
    proc_result = subprocess.run(
        [nvidia_smi, "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
        capture_output=True, text=True
    )
    # Command may return empty if no GPU processes running, but should not fail
    assert proc_result.returncode == 0, f"nvidia-smi process query failed: {proc_result.stderr}"
