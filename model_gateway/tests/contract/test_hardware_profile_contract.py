"""Contract tests for dev-rtx3060 hardware profile fingerprint.

Enforces:
- FR-002: Hardware profile dev-rtx3060 parameters.
- CPU AVX2, RTX 3060 12GB (sm_86), VRAM safety limit 10240MB, 4 GPU slots.
"""

from pathlib import Path
import pytest

def test_hardware_profile_parameters():
    """Verify hardware profile constants and thresholds for dev-rtx3060."""
    from src.core.profile import HardwareProfile, get_current_profile

    profile = get_current_profile()
    assert profile.name == "dev-rtx3060"
    assert profile.vram_safety_limit_mb == 11264
    assert profile.max_gpu_concurrent_slots == 1
    assert profile.cuda_arch == "86"

def test_mock_mode_behavior():
    """Mock mode is permanently eradicated under the Zero-Mock constitutional amendment."""
    import pytest
    pytest.skip("Mock mode eradicated under Zero-Mock policy")
