import pytest
from src.core.gpu_detector import (
    detect_hardware_capabilities,
    detect_gpu_architecture,
    calculate_3axis_dynamic_context,
    GPU_ARCHITECTURE_SPEC_TABLE,
    GpuArchitectureEnum,
)


def test_gpu_architecture_spec_table_completeness():
    """Verify all 5 major SM compute capabilities are defined in the immutable lookup table."""
    assert 6.1 in GPU_ARCHITECTURE_SPEC_TABLE
    assert 7.5 in GPU_ARCHITECTURE_SPEC_TABLE
    assert 8.6 in GPU_ARCHITECTURE_SPEC_TABLE
    assert 8.9 in GPU_ARCHITECTURE_SPEC_TABLE
    assert 12.0 in GPU_ARCHITECTURE_SPEC_TABLE

    pascal = GPU_ARCHITECTURE_SPEC_TABLE[6.1]
    assert pascal.architecture_name == "Pascal"
    assert pascal.supports_flash_attn is False
    assert pascal.recommended_kv_type == "q8_0"

    turing = GPU_ARCHITECTURE_SPEC_TABLE[7.5]
    assert turing.architecture_name == "Turing"
    assert turing.has_tensor_cores is True
    assert turing.supports_fp16_native is True

    ampere = GPU_ARCHITECTURE_SPEC_TABLE[8.6]
    assert ampere.architecture_name == "Ampere"
    assert ampere.supports_flash_attn is True
    assert ampere.supports_bf16_native is True

    ada = GPU_ARCHITECTURE_SPEC_TABLE[8.9]
    assert ada.architecture_name == "Ada Lovelace"
    assert ada.supports_fp8_native is True
    assert ada.recommended_kv_type == "fp8"

    blackwell = GPU_ARCHITECTURE_SPEC_TABLE[12.0]
    assert blackwell.architecture_name == "Blackwell"
    assert blackwell.supports_fp4_native is True
    assert blackwell.recommended_kv_type == "fp4"


def test_3axis_decoupled_synthesis():
    """Test 3-axis decoupled hardware synthesis with diverse mock GPU/VRAM combinations."""
    # Scenario 1: Ada SM 8.9 with 8GB VRAM (e.g. RTX 4060 8GB)
    profile_ada_8gb = detect_hardware_capabilities(
        forced_compute_cap=8.9,
        forced_vram_mb=8192
    )
    assert profile_ada_8gb.gpu_features.architecture_name == "Ada Lovelace"
    assert profile_ada_8gb.use_flash_attn is True
    assert profile_ada_8gb.use_fp8_kv is True
    assert profile_ada_8gb.recommended_model == "qwen3.5-2b"
    assert profile_ada_8gb.dynamic_n_ctx >= 16384

    # Scenario 2: Blackwell SM 12.0 with 8GB VRAM (e.g. RTX 5060 8GB)
    profile_bw_8gb = detect_hardware_capabilities(
        forced_compute_cap=12.0,
        forced_vram_mb=8192
    )
    assert profile_bw_8gb.gpu_features.architecture_name == "Blackwell"
    assert profile_bw_8gb.use_flash_attn is True
    assert profile_bw_8gb.use_fp4_kv is True
    assert profile_bw_8gb.recommended_model == "qwen3.5-2b"
    assert profile_bw_8gb.dynamic_n_ctx >= 32768

    # Scenario 3: Pascal SM 6.1 with 8GB VRAM (e.g. GTX 1070 8GB)
    profile_gtx1070 = detect_hardware_capabilities(
        forced_compute_cap=6.1,
        forced_vram_mb=8192
    )
    assert profile_gtx1070.gpu_features.architecture_name == "Pascal"
    assert profile_gtx1070.use_flash_attn is False
    assert profile_gtx1070.use_q8_kv is True
    assert profile_gtx1070.recommended_model == "qwen3.5-2b"
    assert profile_gtx1070.dynamic_n_ctx == 16384 or profile_gtx1070.dynamic_n_ctx == 32768

    # Scenario 4: Ampere SM 8.6 with 12GB VRAM (e.g. RTX 3060 12GB)
    profile_rtx3060 = detect_hardware_capabilities(
        forced_compute_cap=8.6,
        forced_vram_mb=12288
    )
    assert profile_rtx3060.gpu_features.architecture_name == "Ampere"
    assert profile_rtx3060.use_flash_attn is True
    assert profile_rtx3060.recommended_model == "qwen3.5-4b"
    assert profile_rtx3060.dynamic_n_ctx >= 32768

    # Scenario 5: Blackwell SM 12.0 with 24GB VRAM (e.g. RTX 5080 24GB)
    profile_rtx5080 = detect_hardware_capabilities(
        forced_compute_cap=12.0,
        forced_vram_mb=24576
    )
    assert profile_rtx5080.gpu_features.architecture_name == "Blackwell"
    assert profile_rtx5080.recommended_model == "qwen3.5-9b"
    assert profile_rtx5080.dynamic_n_ctx >= 65536
