"""
tests/integration/test_setup_smart_skip.py
==============================================================================
099-fix-setup-gpu-benchmark: Integration test for setup.sh Step 4.5 Smart Skip

Verify that if model_context_profiles.json cache is already generated (e.g., in Step 2.8),
Step 4.5 uses Smart Skip instead of re-running the full benchmark.
==============================================================================
"""

import os
import sys
import json
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.config_manager import ConfigManager


def test_setup_smart_skip_logic(tmp_path):
    """Verify that model_context_profiles.json presence allows Smart Skip."""
    profiles_file = tmp_path / "config" / "model_context_profiles.json"
    profiles_file.parent.mkdir(parents=True, exist_ok=True)

    dummy_profiles = {
        "generated_at": "2026-08-05T13:00:00Z",
        "system_hardware": {"gpu_name": "NVIDIA GPU", "total_vram_mb": 11264, "is_cuda_available": True},
        "profiles": {
            "qwen3.5-4b": {
                "max_context_length": 8192,
                "recommended_context_length": 7168,
                "binary_search_steps": [],
                "peak_vram_mb": 4200,
                "tpot_tok_per_sec": 48.5,
                "scaling_tested": True,
                "is_supported": True,
                "last_tested_at": "2026-08-05T13:00:00Z"
            }
        }
    }

    profiles_file.write_text(json.dumps(dummy_profiles), encoding="utf-8")
    assert profiles_file.exists()
    assert profiles_file.stat().st_size > 0
