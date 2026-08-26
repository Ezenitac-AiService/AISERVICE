"""
Unit and integration tests for CUDA GPU environment inspection and verification module.
(090-audit-test-refactor: US2)
"""
import pytest
from src.utils.cuda_env import (
    CudaEnvironmentProfile,
    inspect_cuda_environment,
    assert_cuda_environment,
    check_llama_gpu_offload_support,
    get_driver_version,
    get_cuda_version,
    get_gpu_info,
)


def test_get_gpu_info():
    """Verify get_gpu_info detects at least 1 NVIDIA GPU on host."""
    count, names = get_gpu_info()
    assert count >= 1
    assert len(names) >= 1
    assert names[0] != "None"


def test_get_driver_and_cuda_version():
    """Verify driver and CUDA versions are detected as non-empty strings."""
    driver_ver = get_driver_version()
    cuda_ver = get_cuda_version()
    assert driver_ver != "None"
    assert cuda_ver != "None"


def test_inspect_cuda_environment_profile():
    """Verify inspect_cuda_environment returns a complete CudaEnvironmentProfile."""
    profile = inspect_cuda_environment()
    assert isinstance(profile, CudaEnvironmentProfile)
    assert profile.is_cuda_available is True
    assert profile.driver_version != "None"
    assert profile.cuda_version != "None"
    assert profile.gpu_count >= 1
    assert profile.gpu_device_name != "None"
    assert profile.llama_supports_gpu is True


def test_assert_cuda_environment_success():
    """Verify assert_cuda_environment passes without exception on CUDA host."""
    profile = assert_cuda_environment(require_gpu_offload=True)
    assert profile.is_cuda_available is True


def test_assert_cuda_environment_fail_fast(monkeypatch):
    """Verify assert_cuda_environment raises AssertionError when CUDA is unavailable."""
    # Monkeypatch get_gpu_info to simulate non-CUDA environment
    monkeypatch.setattr("src.utils.cuda_env.get_gpu_info", lambda: (0, []))
    with pytest.raises(AssertionError) as exc_info:
        assert_cuda_environment()
    assert "NVIDIA CUDA GPU가 장착되어 있지 않거나" in str(exc_info.value)
