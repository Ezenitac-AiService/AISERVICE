"""
Integration test for build pipeline hardware detection & configuration compatibility.
Validates that get_llama_build_flags() integrates cleanly with ProcessManager and ConfigManager.
"""

import pytest
from src.core.cpu_detector import get_llama_build_flags, detect_cpu_features, detect_gpu_capability
from src.core.config_manager import ConfigManager
from src.core.process_manager import ProcessManager


def test_build_flags_integration_with_config_manager():
    """T012 [US2]: Verifies ConfigManager loads target platform profiles and cpu_detector generates valid flags."""
    cm = ConfigManager()
    profiles = cm.get_platform_profiles()
    assert "dev-rtx3060" in profiles
    assert "legacy-i7-930-gtx1070" in profiles

    dev_profile = cm.get_platform_profile("dev-rtx3060")
    assert dev_profile["compute_capability"] == "8.6"
    assert dev_profile["expected_avx"] is True

    legacy_profile = cm.get_platform_profile("legacy-i7-930-gtx1070")
    assert legacy_profile["compute_capability"] == "6.1"
    assert legacy_profile["expected_avx"] is False


def test_process_manager_verify_build_flags():
    """T012 [US2]: Verifies ProcessManager can access get_llama_build_flags without error."""
    flags = get_llama_build_flags()
    assert flags.ggml_cuda is True
    assert flags.cmake_args_str.startswith("-DGGML_CUDA=ON")
    assert "-DCMAKE_CUDA_ARCHITECTURES=" in flags.cmake_args_str
