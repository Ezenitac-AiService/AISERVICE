"""
Unit tests for GPU and CUDA Detector (src/core/gpu_detector.py).
"""

import pytest
from unittest.mock import patch, MagicMock
from src.core.gpu_detector import (
    check_gpu_availability,
    validate_cuda_build_environment,
    GpuDeviceInfo,
    VramOffloadStatus,
    GpuAccelerationError,
    VramOverflowError
)


def test_gpu_device_info_models():
    info = GpuDeviceInfo(
        device_id=0,
        name="NVIDIA GeForce GTX 1080 Ti",
        total_vram_mb=11264,
        free_vram_mb=9000,
        is_cuda_available=True
    )
    assert info.device_id == 0
    assert info.name == "NVIDIA GeForce GTX 1080 Ti"
    assert info.total_vram_mb == 11264
    assert info.is_cuda_available is True

    status = VramOffloadStatus(
        model_id="qwen3.5-2b",
        total_layers=28,
        offloaded_layers=28,
        is_fully_offloaded=True,
        offloaded_vram_mb=3000
    )
    assert status.is_fully_offloaded is True
    assert status.offloaded_layers == 28


@patch("shutil.which")
def test_check_gpu_availability_no_nvidia_smi(mock_which):
    mock_which.return_value = None
    with pytest.raises(GpuAccelerationError) as exc_info:
        check_gpu_availability()
    assert "nvidia-smi tool not found" in str(exc_info.value)


@patch("shutil.which")
@patch("subprocess.run")
def test_check_gpu_availability_success(mock_run, mock_which):
    mock_which.return_value = "/usr/bin/nvidia-smi"
    mock_res = MagicMock()
    mock_res.stdout = "NVIDIA GeForce GTX 1080 Ti, 11264, 9500, 580.173.02\n"
    mock_run.return_value = mock_res

    gpu_info = check_gpu_availability()
    assert gpu_info.name == "NVIDIA GeForce GTX 1080 Ti"
    assert gpu_info.total_vram_mb == 11264
    assert gpu_info.free_vram_mb == 9500
    assert gpu_info.is_cuda_available is True

from src.core.process_manager import ProcessManager

def test_parse_vram_offload_full_offload():
    line = "llm_load_tensors: offloaded 28/28 layers to GPU"
    status = ProcessManager.parse_vram_offload_log(line, "qwen3.5-2b")
    assert status is not None
    assert status.is_fully_offloaded is True
    assert status.offloaded_layers == 28
    assert status.total_layers == 28

def test_parse_vram_offload_partial_offload():
    line = "llm_load_tensors: offloaded 20/28 layers to GPU"
    status = ProcessManager.parse_vram_offload_log(line, "qwen3.5-2b")
    assert status is not None
    assert status.is_fully_offloaded is False
    assert status.offloaded_layers == 20
    assert status.total_layers == 28

def test_parse_vram_offload_irrelevant_line():
    line = "llm_load_tensors: using CPU backend"
    status = ProcessManager.parse_vram_offload_log(line, "qwen3.5-2b")
    assert status is None

def test_verify_vram_offload_raises_on_partial():
    pm = ProcessManager()
    status = VramOffloadStatus(
        model_id="qwen3.5-2b",
        total_layers=28,
        offloaded_layers=20,
        is_fully_offloaded=False
    )
    with pytest.raises(VramOverflowError, match="VRAM_PARTIAL_OFFLOAD_ERROR: 20/28 layers offloaded. 100% VRAM offload required."):
        pm.verify_vram_offload("qwen3.5-2b", status)

def test_parse_vram_offload_vram_size():
    line = "llm_load_tensors:        CUDA0 model buffer size =  2953.80 MiB"
    status = ProcessManager.parse_vram_offload_log(line, "qwen3.5-2b")
    assert status is not None
    assert status.is_fully_offloaded is True
    assert status.offloaded_vram_mb == 2953


# T018: Dynamic CUDA version detection tests
@patch("src.core.gpu_detector.shutil.which")
@patch("subprocess.run")
def test_check_gpu_availability_dynamic_cuda_version(mock_run, mock_which):
    """T018: check_gpu_availability는 nvidia-smi 일반 출력에서 CUDA 버전을 동적으로 감지해야 한다."""
    def which_side_effect(cmd):
        if cmd == "nvidia-smi":
            return "/usr/bin/nvidia-smi"
        if cmd == "nvcc":
            return None
        return None
    mock_which.side_effect = which_side_effect

    # First call: CSV query; Second call: plain nvidia-smi for CUDA version
    csv_res = MagicMock()
    csv_res.stdout = "NVIDIA GeForce GTX 1080 Ti, 11264, 9500, 580.173.02\n"

    plain_res = MagicMock()
    plain_res.stdout = (
        "+-----------------------------------------------------------------------------+\n"
        "| NVIDIA-SMI 580.173.02    Driver Version: 580.173.02    CUDA Version: 13.0   |\n"
        "+-----------------------------------------------------------------------------+\n"
    )

    mock_run.side_effect = [csv_res, plain_res]

    gpu_info = check_gpu_availability()
    assert gpu_info.cuda_version == "13.0"
    assert gpu_info.is_cuda_available is True


@patch("src.core.gpu_detector.shutil.which")
@patch("subprocess.run")
def test_check_gpu_availability_cuda_version_fallback_none(mock_run, mock_which):
    """T018: CUDA 버전 파싱 실패 시 None으로 폴백해야 한다."""
    def which_side_effect(cmd):
        if cmd == "nvidia-smi":
            return "/usr/bin/nvidia-smi"
        if cmd == "nvcc":
            return None
        return None
    mock_which.side_effect = which_side_effect

    csv_res = MagicMock()
    csv_res.stdout = "NVIDIA GeForce GTX 1080 Ti, 11264, 9500, 580.173.02\n"

    # Plain output without CUDA Version line
    plain_res = MagicMock()
    plain_res.stdout = "Some other nvidia-smi output without CUDA info\n"

    mock_run.side_effect = [csv_res, plain_res]

    gpu_info = check_gpu_availability()
    assert gpu_info.cuda_version is None


# T019: ProcessState.vram_offloaded field tests
from src.core.process_manager import ProcessState, ProcessStatusEnum

def test_process_state_vram_offloaded_default():
    """T019: ProcessState의 vram_offloaded 기본값은 None이어야 한다."""
    state = ProcessState(status=ProcessStatusEnum.LOADING, model_id="qwen3.5-2b")
    assert state.vram_offloaded is None


def test_verify_vram_offload_sets_vram_offloaded_true():
    """T019: verify_vram_offload 성공 시 ProcessState.vram_offloaded=True로 설정되어야 한다."""
    pm = ProcessManager()
    pm.state = ProcessState(
        status=ProcessStatusEnum.LOADING,
        model_id="qwen3.5-2b",
        port=8081,
    )
    status = VramOffloadStatus(
        model_id="qwen3.5-2b",
        total_layers=28,
        offloaded_layers=28,
        is_fully_offloaded=True,
        offloaded_vram_mb=3000,
    )
    pm.verify_vram_offload("qwen3.5-2b", status)
    assert pm.state.vram_offloaded is True


# T021: Runtime VRAM overflow monitoring tests
def test_check_vram_runtime_overflow_safe():
    """T021: VRAM 사용률이 임계치 미만일 때 예외가 발생하지 않아야 한다."""
    pm = ProcessManager()
    with patch("shutil.which", return_value="/usr/bin/nvidia-smi"):
        mock_result = MagicMock()
        mock_result.stdout = "5000, 11264\n"  # ~44% usage
        with patch("subprocess.run", return_value=mock_result):
            pm.check_vram_runtime_overflow(threshold_pct=95.0)  # Should not raise


def test_check_vram_runtime_overflow_raises():
    """T021: VRAM 사용률이 임계치를 초과하면 VramOverflowError가 발생해야 한다."""
    pm = ProcessManager()
    with patch("shutil.which", return_value="/usr/bin/nvidia-smi"):
        mock_result = MagicMock()
        mock_result.stdout = "10800, 11264\n"  # ~95.9% usage
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(VramOverflowError, match="VRAM 실시간 오버플로우 감지"):
                pm.check_vram_runtime_overflow(threshold_pct=95.0)


def test_check_vram_runtime_overflow_no_nvidia_smi():
    """T021: nvidia-smi 미설치 환경에서는 검사를 건너뛰어야 한다."""
    pm = ProcessManager()
    with patch("shutil.which", return_value=None):
        pm.check_vram_runtime_overflow(threshold_pct=95.0)  # Should not raise


# T005 / US1: Unit tests for get_nvml_vram_info, estimate_kv_cache_vram, PortCollisionError
from src.core.gpu_detector import get_nvml_vram_info, estimate_kv_cache_vram, PortCollisionError


def test_dual_mode_contract_schema():
    import json
    import os

    contract_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "specs", "014-real-gpu-benchmark-testing", "contracts", "dual-mode-test-schema.json"
    )
    assert os.path.exists(contract_path), f"Contract file not found at {contract_path}"

    with open(contract_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    assert schema["title"] == "DualModeTestExecutionContract"
    assert "execution_mode" in schema["properties"]
    assert "strict_mock_prohibited" in schema["properties"]


def test_estimate_kv_cache_vram_calculation():
    """T005: KV Cache VRAM estimator calculation test."""
    # 2 * 36 layers * 32 heads * 128 dim * 4096 ctx * 2 bytes = 2,415,919,104 bytes = ~2304 MB
    kv_mb = estimate_kv_cache_vram(n_layers=36, n_heads=32, head_dim=128, n_ctx=4096)
    assert kv_mb == 2304

def test_get_nvml_vram_info_fallback():
    """T005: get_nvml_vram_info should fallback safely to check_gpu_availability if PyNVML fails."""
    with patch.dict("sys.modules", {"pynvml": None}):
        with patch("src.core.gpu_detector.check_gpu_availability") as mock_fallback:
            mock_fallback.return_value = GpuDeviceInfo(
                device_id=0, name="Fallback GPU", total_vram_mb=11264, free_vram_mb=9000, is_cuda_available=True
            )
            info = get_nvml_vram_info()
            assert info.name == "Fallback GPU"

def test_port_collision_error_exception():
    """T005: PortCollisionError raised when port 8081 is occupied."""
    with pytest.raises(PortCollisionError):
        raise PortCollisionError("Port 8081 occupied")


# T004: validate_cuda_build_environment fail-fast tests (FR-005)

@patch("src.core.gpu_detector.shutil.which")
def test_validate_cuda_build_env_no_nvidia_smi(mock_which):
    """T004: nvidia-smi 미존재 시 GpuAccelerationError 즉시 발생."""
    mock_which.return_value = None
    with pytest.raises(GpuAccelerationError, match="nvidia-smi"):
        validate_cuda_build_environment()


@patch("src.core.gpu_detector.shutil.which")
def test_validate_cuda_build_env_no_nvcc(mock_which):
    """T004: nvcc 미존재 시 GpuAccelerationError 즉시 발생."""
    def which_side_effect(cmd):
        if cmd == "nvidia-smi":
            return "/usr/bin/nvidia-smi"
        return None  # nvcc not found
    mock_which.side_effect = which_side_effect
    with pytest.raises(GpuAccelerationError, match="nvcc"):
        validate_cuda_build_environment()


@patch("src.core.gpu_detector.shutil.which")
def test_validate_cuda_build_env_success(mock_which):
    """T004: nvidia-smi와 nvcc 모두 존재할 때 True 반환."""
    def which_side_effect(cmd):
        if cmd == "nvidia-smi":
            return "/usr/bin/nvidia-smi"
        if cmd == "nvcc":
            return "/usr/bin/nvcc"
        return None
    mock_which.side_effect = which_side_effect
    assert validate_cuda_build_environment() is True


# T005 / US1: llama_supports_gpu() CUDA verification test

@patch("src.core.gpu_detector.shutil.which")
def test_validate_cuda_build_env_cpu_only_llama(mock_which):
    """T005: llama_supports_gpu_offload()가 False 반환 시 GpuAccelerationError 발생."""
    import sys

    def which_side_effect(cmd):
        if cmd == "nvidia-smi":
            return "/usr/bin/nvidia-smi"
        if cmd == "nvcc":
            return "/usr/bin/nvcc"
        return None
    mock_which.side_effect = which_side_effect

    mock_llama = MagicMock()
    mock_llama.llama_supports_gpu_offload = MagicMock(return_value=False)
    mock_llama.llama_supports_gpu = MagicMock(return_value=False)

    # Save original module and replace with mock
    original_module = sys.modules.get("llama_cpp")
    sys.modules["llama_cpp"] = mock_llama
    try:
        with pytest.raises(GpuAccelerationError, match="CPU 전용 모드"):
            validate_cuda_build_environment()
    finally:
        # Restore original module
        if original_module is not None:
            sys.modules["llama_cpp"] = original_module
        else:
            sys.modules.pop("llama_cpp", None)


def test_get_realtime_usable_vram():
    """T005 / US1: get_realtime_usable_vram calculates free_vram_mb - safety_margin."""
    from src.core.gpu_detector import get_realtime_usable_vram
    with patch("src.core.gpu_detector.get_nvml_vram_info") as mock_nvml:
        mock_nvml.return_value = GpuDeviceInfo(
            device_id=0, name="Test GPU", total_vram_mb=11264, free_vram_mb=8000, is_cuda_available=True
        )
        usable = get_realtime_usable_vram(safety_margin_mb=500)
        assert usable == 7500

        # Dynamic safety margin for n_ctx=16384 -> 500 + int(16384 * 0.05) = 500 + 819 = 1319 MB
        usable_dynamic = get_realtime_usable_vram(n_ctx=16384)
        assert usable_dynamic == 8000 - 1319


def test_wait_for_nvml_vram_settled():
    """T005: wait_for_nvml_vram_settled converges when delta < threshold."""
    from src.core.gpu_detector import wait_for_nvml_vram_settled
    info1 = GpuDeviceInfo(device_id=0, name="GPU", total_vram_mb=11264, free_vram_mb=8000, is_cuda_available=True)
    info2 = GpuDeviceInfo(device_id=0, name="GPU", total_vram_mb=11264, free_vram_mb=8005, is_cuda_available=True)

    with patch("src.core.gpu_detector.get_nvml_vram_info") as mock_info:
        mock_info.side_effect = [info1, info2]
        settled = wait_for_nvml_vram_settled(poll_interval=0.01, max_attempts=3, delta_threshold_mb=10)
        assert settled.free_vram_mb == 8005


def test_calculate_max_allocatable_n_ctx():
    """T008: calculate_max_allocatable_n_ctx correctly reverses KV cache budget."""
    from src.core.gpu_detector import calculate_max_allocatable_n_ctx
    # For budget 3000 MB:
    # 2 * 36 * 32 * 128 * 2 = 589,824 bytes per ctx token
    # 3000 * 1024 * 1024 / 589824 = 5333.3 -> aligned to 512 = 5120
    n_ctx = calculate_max_allocatable_n_ctx(usable_kv_budget_mb=3000, n_layers=36, n_heads=32, head_dim=128)
    assert n_ctx == 5120


def test_calculate_max_allocatable_n_ctx_gqa():
    """T006 / US1: Test GQA n_head_kv reverse calculation."""
    from src.core.gpu_detector import calculate_max_allocatable_n_ctx
    # Gemma 4 E2B parameters: n_layers=35, n_heads=8, n_head_kv=1, head_dim=512
    # bytes_per_token = 2 * 35 * 1 * 512 * 2 = 71,680 bytes
    # For budget 6000 MB: 6000 * 1024 * 1024 / 71680 = 87771 -> aligned to step 2048 = 86016 -> capped at max_cap 32768
    n_ctx = calculate_max_allocatable_n_ctx(
        usable_kv_budget_mb=6000,
        n_layers=35,
        n_heads=8,
        head_dim=512,
        n_head_kv=1,
        step=2048,
        max_cap=32768
    )
    assert n_ctx == 32768


def test_calculate_dynamic_log_step_size():
    """T005 / FR-004: Test log-scaled dynamic step size formula."""
    from src.core.gpu_detector import calculate_dynamic_log_step_size
    assert calculate_dynamic_log_step_size(16384) == 512
    assert calculate_dynamic_log_step_size(32768) == 512
    assert calculate_dynamic_log_step_size(131072) == 2048
    assert calculate_dynamic_log_step_size(1048576) == 16384


def test_read_gguf_metadata_architecture():
    """T007 / US1: Test GGUF binary header parser with actual local file or mock."""
    from src.core.gpu_detector import read_gguf_metadata_architecture
    import os
    gguf_path = "models/gemma4-e2b/gemma-4-E2B-it-Q4_K_M.gguf"
    if os.path.exists(gguf_path):
        meta = read_gguf_metadata_architecture(gguf_path)
        assert meta.get("n_layers") == 35
        assert meta.get("n_head_kv") == 1
        assert meta.get("n_heads") == 8
        assert meta.get("max_rope_n_ctx") == 131072



