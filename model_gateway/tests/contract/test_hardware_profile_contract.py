"""Contract tests for dev-rtx3060 hardware profile fingerprint.

Enforces:
- FR-002: Hardware profile dev-rtx3060 parameters.
- CPU AVX2, RTX 3060 12GB (sm_86), VRAM safety limit 10240MB, 4 GPU slots.
"""

from pathlib import Path
import pytest

def test_hardware_profile_parameters():
    """Verify hardware profile constants and thresholds for dev-rtx3060."""
    from AISERVICE.model_gateway.src.core.profile import HardwareProfile, get_current_profile

    profile = get_current_profile()
    assert profile.name == "dev-rtx3060"
    assert profile.vram_safety_limit_mb == 10240
    assert profile.max_gpu_concurrent_slots == 4
    assert profile.cuda_arch == "86"

def test_mock_mode_behavior(monkeypatch):
    """When MOCK_LLAMA_SERVER=1, engine provides mock evidence without failing hardware checks."""
    from AISERVICE.model_gateway.src.core.profile import is_mock_mode_active

    monkeypatch.setenv("MOCK_LLAMA_SERVER", "1")
    assert is_mock_mode_active() is True

    monkeypatch.setenv("MOCK_LLAMA_SERVER", "0")
    assert is_mock_mode_active() is False
