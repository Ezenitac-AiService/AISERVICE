"""
tests/unit/test_positive_tps_profile.py
==============================================================================
099-fix-setup-gpu-benchmark: Unit test for is_supported positive TPS profile recording

Verify that supported models have is_supported=True, tpot_tok_per_sec > 0.0,
and peak_vram_mb > 0 in model_context_profiles.json.
==============================================================================
"""

import os
import sys
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.config_manager import ConfigManager
from scripts.benchmark_context_window import save_benchmark_profile


def test_positive_tps_profile_schema_saving(tmp_path):
    """Verify supported model profile entry contains positive TPS and is_supported=True."""
    cfg_mgr = ConfigManager(config_path=str(tmp_path / "model_config.json"))

    mock_profile_entry = {
        "max_context_length": 8192,
        "recommended_context_length": 7168,
        "binary_search_steps": [
            {"step": 1, "tested_n_ctx": 8192, "real_vram_mb": 4200, "status": "PASS"}
        ],
        "peak_vram_mb": 4200,
        "tpot_tok_per_sec": 48.5,
        "scaling_tested": True,
        "is_supported": True,
        "last_tested_at": "2026-08-05T13:00:00Z"
    }

    res_profiles = {
        "generated_at": "2026-08-05T13:00:00Z",
        "system_hardware": {
            "gpu_name": "NVIDIA GPU",
            "total_vram_mb": 11264,
            "is_cuda_available": True
        },
        "profiles": {
            "qwen3.5-4b": mock_profile_entry
        }
    }

    cfg_mgr.save_model_context_profiles(res_profiles)

    saved_data = cfg_mgr.load_model_context_profiles()
    assert "qwen3.5-4b" in saved_data.get("profiles", {})
    entry = saved_data["profiles"]["qwen3.5-4b"]
    assert entry["is_supported"] is True
    assert entry["tpot_tok_per_sec"] > 0.0
    assert entry["peak_vram_mb"] > 0
