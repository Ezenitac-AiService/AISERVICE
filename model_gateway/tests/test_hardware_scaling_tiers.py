"""
Unit tests for Spec 036: Hardware Context Scaling Tiers, Dynamic Model Recommendation,
and TPS SLA Guard.
"""

import pytest
from src.core.gpu_detector import (
    detect_hardware_capabilities,
    HardwareTierEnum,
    GpuArchitectureEnum,
    calculate_3axis_dynamic_context,
)
from src.core.process_manager import ProcessManager, ProcessStatusEnum


def test_baseline_8gb_tier():
    """Verify GTX 1070 8GB baseline hardware tier configuration."""
    profile = detect_hardware_capabilities(
        forced_compute_cap=6.1,
        forced_vram_mb=8192
    )
    assert profile.hardware_tier == HardwareTierEnum.BASELINE_8GB
    assert profile.recommended_model == "qwen3.5-2b"
    assert profile.recommended_batch_model == "qwen3.5-4b"
    assert profile.resident_standard_n_ctx == 65536
    assert profile.resident_ultra_n_ctx == 131072
    assert profile.batch_n_ctx == 32768
    assert profile.min_target_tps == 50.0
    assert profile.use_flash_attn is False
    assert profile.use_q8_kv is True


def test_mid_12gb_16gb_tier():
    """Verify RTX 3060 12GB / RTX 4070 16GB tier configuration."""
    profile = detect_hardware_capabilities(
        forced_compute_cap=8.6,
        forced_vram_mb=12288
    )
    assert profile.hardware_tier == HardwareTierEnum.MID_12GB_16GB
    assert profile.recommended_model == "qwen3.5-4b"
    assert profile.recommended_batch_model == "qwen3.5-9b"
    assert profile.resident_standard_n_ctx == 32768
    assert profile.resident_ultra_n_ctx == 65536
    assert profile.batch_n_ctx == 32768
    assert profile.min_target_tps == 40.0
    assert profile.use_flash_attn is True


def test_high_20gb_40gb_tier():
    """Verify RTX 3090 / 4090 24GB tier configuration."""
    profile = detect_hardware_capabilities(
        forced_compute_cap=8.9,
        forced_vram_mb=24576
    )
    assert profile.hardware_tier == HardwareTierEnum.HIGH_20GB_40GB
    assert profile.recommended_model == "qwen3.5-9b"
    assert profile.recommended_batch_model == "gemma4-12b"
    assert profile.resident_standard_n_ctx == 65536
    assert profile.resident_ultra_n_ctx == 131072
    assert profile.batch_n_ctx == 32768
    assert profile.min_target_tps == 35.0


def test_ultra_40gb_plus_tier():
    """Verify A100 / H100 80GB enterprise tier configuration."""
    profile = detect_hardware_capabilities(
        forced_compute_cap=9.0,
        forced_vram_mb=81920
    )
    assert profile.hardware_tier == HardwareTierEnum.ULTRA_40GB_PLUS
    assert profile.recommended_model == "qwen3.6-27b"
    assert profile.recommended_batch_model == "qwen3.6-35b-a3b"
    assert profile.resident_standard_n_ctx == 131072
    assert profile.resident_ultra_n_ctx == 131072
    assert profile.batch_n_ctx == 131072
    assert profile.min_target_tps == 30.0


def test_tps_sla_monitoring_and_breach():
    """Test ProcessManager TPS recording and SLA evaluation logic."""
    pm = ProcessManager()
    
    # Initially no samples
    sla_met, avg_tps, msg = pm.evaluate_tps_sla(is_realtime=True)
    assert sla_met is True
    assert avg_tps == 0.0

    # Record high TPS samples (> 50 TPS)
    for _ in range(5):
        pm.record_tps_sample(55.0, "qwen3.5-2b")
    
    sla_met, avg_tps, msg = pm.evaluate_tps_sla(is_realtime=True)
    assert sla_met is True
    assert avg_tps == 55.0

    # Record degraded TPS samples (< 20 TPS) to simulate SLA breach
    for _ in range(20):
        pm.record_tps_sample(18.0, "qwen3.5-4b")

    sla_met, avg_tps, msg = pm.evaluate_tps_sla(is_realtime=True)
    assert sla_met is False
    assert avg_tps == 18.0
    assert "TPS SLA Breach" in msg


def test_hardware_limits_context_bounds():
    """Verify ProcessManager hardware limits reflect extended contexts."""
    pm = ProcessManager()
    assert pm.hardware_limits["qwen3.5-2b"] >= 131072
    assert pm.hardware_limits["qwen3.5-4b"] >= 49152
    assert pm.hardware_limits["qwen3.5-9b"] >= 32768
