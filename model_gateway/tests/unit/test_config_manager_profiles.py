import pytest
import os
import json
import tempfile
from src.core.config_manager import ConfigManager, ModelContextProfileEntry


def test_model_context_profile_entry_validation():
    """T005: Validate ModelContextProfileEntry Pydantic schema with is_supported field."""
    valid_data = {
        "max_context_length": 8192,
        "recommended_context_length": 7168,
        "binary_search_steps": [{"step": 1, "tested_n_ctx": 8192, "status": "PASS"}],
        "peak_vram_mb": 4200,
        "tpot_tok_per_sec": 45.0,
        "scaling_tested": True,
        "is_supported": True,
        "last_tested_at": "2026-08-05T12:00:00Z"
    }
    entry = ModelContextProfileEntry(**valid_data)
    assert entry.max_context_length == 8192
    assert entry.is_supported is True

    unsupported_data = {
        "max_context_length": 2048,
        "recommended_context_length": 2048,
        "is_supported": False
    }
    entry_unsupported = ModelContextProfileEntry(**unsupported_data)
    assert entry_unsupported.is_supported is False
    assert entry_unsupported.recommended_context_length == 2048


def test_atomic_save_and_merge_profiles(tmp_path):
    """T005: Validate profile loading, atomic saving, and profile dictionary merge."""
    cfg_file = str(tmp_path / "server_config.json")
    mgr = ConfigManager(config_path=cfg_file)

    profiles_file = str(tmp_path / "model_context_profiles.json")

    initial_data = {
        "generated_at": "2026-08-05T12:00:00Z",
        "system_hardware": {"gpu_name": "Test GPU"},
        "profiles": {
            "qwen3.5-4b": {
                "max_context_length": 4096,
                "recommended_context_length": 3584,
                "is_supported": True
            }
        }
    }
    mgr.save_model_context_profiles(initial_data)

    loaded = mgr.load_model_context_profiles()
    assert "qwen3.5-4b" in loaded["profiles"]
    assert loaded["profiles"]["qwen3.5-4b"]["is_supported"] is True

    # Test merging new model profile
    loaded["profiles"]["gemma4-e2b"] = {
        "max_context_length": 8192,
        "recommended_context_length": 7168,
        "is_supported": True
    }
    mgr.save_model_context_profiles(loaded)

    reloaded = mgr.load_model_context_profiles()
    assert len(reloaded["profiles"]) == 2
    assert "gemma4-e2b" in reloaded["profiles"]
