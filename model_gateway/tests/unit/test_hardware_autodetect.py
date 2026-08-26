"""
Unit & Integration tests for 3-tier Multi-Platform Hardware Auto-Detection & Optimization.
Feature: 094-hardware-capability-autodetect
Tests 3 target hardware profiles:
1. TRAIN_RTX3060 (Ampere sm_86, AVX2=True, 3rd Gen Tensor Cores, TF32, BF16, FlashAttention-2)
2. SVC_GTX1070_I7_930 (Pascal sm_61, AVX2=False, SSE4.2, FP16, SDPA)
3. DEV_GTX1080TI (Pascal sm_61, AVX2=True, FP16, SDPA)
"""

import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch

from src.core.cpu_detector import (
    HardwareProfileCapability,
    detect_cpu_features,
    detect_gpu_capability_safe,
    get_llama_build_flags,
    get_hardware_profile_capability,
    match_platform_profile
)


def test_contract_schema_exists():
    """Verify hardware autodetect contract JSON schema exists and is valid."""
    contract_path = Path(__file__).parent.parent.parent / "specs" / "094-hardware-capability-autodetect" / "contracts" / "hardware_autodetect_contract.json"
    assert contract_path.exists(), "hardware_autodetect_contract.json contract file missing"
    
    with open(contract_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    assert schema.get("title") == "HardwareAutodetectContract"
    assert "detected_platform" in schema["properties"]


def test_train_rtx3060_profile_detection():
    """
    US1 & FR-002: Verify RTX 3060 (Ampere sm_86, AVX2=True) profile detection and full acceleration flags.
    Should enable 3rd Gen Tensor Cores, TF32, BF16, and FlashAttention-2 (LLAMA_FLASH_ATTN=ON).
    """
    mock_env = {
        "MOCK_COMPUTE_CAPABILITY": "8.6",
        "MOCK_GPU_NAME": "NVIDIA GeForce RTX 3060",
        "MOCK_CPU_AVX2": "1"
    }
    with patch.dict(os.environ, mock_env):
        hw_cap = get_hardware_profile_capability()
        flags = get_llama_build_flags()

        assert hw_cap.platform_type == "TRAIN_RTX3060"
        assert hw_cap.compute_capability == 8.6
        assert hw_cap.cuda_arch_code == "86"
        assert hw_cap.cpu_avx2_supported is True
        assert hw_cap.tensor_cores_gen == 3
        assert hw_cap.supports_tf32 is True
        assert hw_cap.supports_bf16 is True
        assert hw_cap.supports_flash_attn2 is True
        
        assert "-DGGML_FLASH_ATTN=ON" in flags.cmake_args_list
        assert "-DGGML_CUDA_FA_ALL=ON" in flags.cmake_args_list
        assert "-DCMAKE_CUDA_ARCHITECTURES=86" in flags.cmake_args_list


def test_svc_gtx1070_i7_930_profile_detection():
    """
    US2 & FR-003, FR-006: Verify i7-930 + GTX 1070 (Pascal sm_61, AVX2=False) CPU bottleneck profile.
    Should bypass AVX2 (-DGGML_AVX2=OFF) to prevent SIGILL crash and disable FlashAttention-2 (-DGGML_FLASH_ATTN=OFF).
    """
    mock_env = {
        "MOCK_COMPUTE_CAPABILITY": "6.1",
        "MOCK_GPU_NAME": "NVIDIA GeForce GTX 1070",
        "MOCK_CPU_AVX2": "0"
    }
    with patch.dict(os.environ, mock_env):
        hw_cap = get_hardware_profile_capability()
        flags = get_llama_build_flags()

        assert hw_cap.platform_type == "SVC_GTX1070_I7_930"
        assert hw_cap.compute_capability == 6.1
        assert hw_cap.cuda_arch_code == "61"
        assert hw_cap.cpu_avx2_supported is False
        assert hw_cap.tensor_cores_gen == 0
        assert hw_cap.supports_tf32 is False
        assert hw_cap.supports_bf16 is False
        assert hw_cap.supports_flash_attn2 is False

        assert "-DGGML_AVX2=OFF" in flags.cmake_args_list
        assert "-DGGML_FLASH_ATTN=OFF" in flags.cmake_args_list
        assert "-DGGML_CUDA_FA_ALL=ON" not in flags.cmake_args_list


def test_dev_gtx1080ti_profile_detection():
    """
    US2 & FR-003: Verify GTX 1080Ti (Pascal sm_61, AVX2=True) profile.
    Should enable AVX2 (-DGGML_AVX2=ON) but disable FlashAttention-2 (-DGGML_FLASH_ATTN=OFF) due to Pascal architecture.
    """
    mock_env = {
        "MOCK_COMPUTE_CAPABILITY": "6.1",
        "MOCK_GPU_NAME": "NVIDIA GeForce GTX 1080 Ti",
        "MOCK_CPU_AVX2": "1"
    }
    with patch.dict(os.environ, mock_env):
        hw_cap = get_hardware_profile_capability()
        flags = get_llama_build_flags()

        assert hw_cap.platform_type == "DEV_GTX1080TI"
        assert hw_cap.compute_capability == 6.1
        assert hw_cap.cpu_avx2_supported is True
        assert hw_cap.tensor_cores_gen == 0
        assert hw_cap.supports_flash_attn2 is False

        assert "-DGGML_AVX2=ON" in flags.cmake_args_list
        assert "-DGGML_FLASH_ATTN=OFF" in flags.cmake_args_list


def test_hardware_capability_entity_model():
    """Verify HardwareProfileCapability data entity creation and serialization."""
    entity = HardwareProfileCapability(
        platform_type="TRAIN_RTX3060",
        cpu_model="Intel Core i7-4770",
        cpu_avx2_supported=True,
        gpu_name="NVIDIA GeForce RTX 3060",
        compute_capability=8.6,
        cuda_arch_code="86",
        tensor_cores_gen=3,
        supports_tf32=True,
        supports_bf16=True,
        supports_flash_attn2=True,
        cmake_args=["-DGGML_CUDA=ON", "-DGGML_FLASH_ATTN=ON"],
        recommended_runtime_flags={"n_gpu_layers": 99, "flash_attn": True}
    )
    
    data = entity.model_dump()
    assert data["platform_type"] == "TRAIN_RTX3060"
    assert data["tensor_cores_gen"] == 3
    assert data["supports_bf16"] is True
    assert data["recommended_runtime_flags"]["flash_attn"] is True
