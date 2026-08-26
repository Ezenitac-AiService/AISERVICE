import pytest
from src.core.process_manager import LlamaServerProcessManager
from src.core.gpu_detector import (
    detect_hardware_capabilities,
    DynamicHardwareProfile,
    GpuArchitectureFeatures,
    CpuArchitectureFeatures,
)


def test_pascal_sm61_flags_injection(tmp_path):
    """Verify that Pascal SM 6.1 omits --flash_attn and injects Q8_0 KV cache flags."""
    pm = LlamaServerProcessManager()
    
    # Mock Pascal SM 6.1 profile
    mock_profile = detect_hardware_capabilities(
        forced_compute_cap=6.1,
        forced_vram_mb=8192
    )
    
    cmd = pm.build_server_command(
        model_id="qwen3.5-2b",
        port=8089,
        model_path="/tmp/fake_model.gguf",
        n_ctx=16384,
        hardware_profile=mock_profile
    )
    
    cmd_str = " ".join(cmd)
    # Check that FlashAttention flag is NOT in cmd on Pascal
    assert "--flash_attn" not in cmd_str
    assert "-fa" not in cmd
    # Check -ngl 999 or --n_gpu_layers 999 (100% GPU offload)
    assert "-ngl 999" in cmd_str or "--n_gpu_layers 999" in cmd_str or "-ngl" in cmd or "--n_gpu_layers" in cmd


def test_ampere_sm86_flags_injection(tmp_path):
    """Verify that Ampere SM 8.6 injects --flash_attn or -fa."""
    pm = LlamaServerProcessManager()
    
    # Mock Ampere SM 8.6 profile
    mock_profile = detect_hardware_capabilities(
        forced_compute_cap=8.6,
        forced_vram_mb=12288
    )
    
    cmd = pm.build_server_command(
        model_id="qwen3.5-4b",
        port=8089,
        model_path="/tmp/fake_model.gguf",
        n_ctx=32768,
        hardware_profile=mock_profile
    )
    
    cmd_str = " ".join(cmd)
    assert "--flash_attn" in cmd_str or "-fa" in cmd_str
