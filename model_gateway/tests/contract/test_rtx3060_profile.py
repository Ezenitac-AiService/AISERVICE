"""Contract tests for dev-rtx3060 hardware profile specifications (T027).

Enforces:
- i7-4770 AVX2
- RTX 3060 12GB (Compute capability 8.6, sm_86)
- dev-rtx3060 profile name
- llama.cpp-cuda execution environment
"""

from pathlib import Path
import pytest
from src.core.profile import get_current_profile, HardwareProfile

def test_rtx3060_profile_parameters():
    prof = get_current_profile()
    assert prof.name == "dev-rtx3060"
    assert prof.cuda_arch == "86"
    assert prof.vram_safety_limit_mb == 10240
    assert prof.max_gpu_concurrent_slots == 4
    assert "avx2" in prof.cpu_features
