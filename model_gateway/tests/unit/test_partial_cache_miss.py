import pytest
import os
import json
from scripts.benchmark_context_window import get_candidate_llm_models, sync_partial_cache_miss
from src.core.config_manager import ConfigManager


def test_get_candidate_llm_models():
    """T008 [US1]: Test LLM candidate model extraction excluding embedding and rerank."""
    llm_models = get_candidate_llm_models()
    assert isinstance(llm_models, list)
    assert len(llm_models) >= 2
    assert "bge-m3" not in llm_models
    assert "bge-reranker-v2-m3" not in llm_models


def test_sync_partial_cache_miss(tmp_path):
    """T008 [US1]: Test Partial Cache Miss pinpoint sync logic."""
    cfg_file = str(tmp_path / "server_config.json")
    mgr = ConfigManager(config_path=cfg_file)

    profiles_file = str(tmp_path / "model_context_profiles.json")
    initial_profiles = {
        "generated_at": "2026-08-05T12:00:00Z",
        "profiles": {
            "gemma4-e2b": {
                "max_context_length": 4096,
                "recommended_context_length": 3584,
                "is_supported": True
            }
        }
    }
    with open(profiles_file, "w", encoding="utf-8") as f:
        json.dump(initial_profiles, f)

    catalog_llm = ["gemma4-e2b", "qwen3.5-4b"]
    missing = set(catalog_llm) - set(initial_profiles["profiles"].keys())
    assert missing == {"qwen3.5-4b"}

    synced_missing = sync_partial_cache_miss(
        catalog_models=catalog_llm,
        profiles_file_path=profiles_file,
        mock_sync=True
    )
    assert synced_missing == ["qwen3.5-4b"]

    with open(profiles_file, "r", encoding="utf-8") as f:
        updated = json.load(f)

    assert "qwen3.5-4b" in updated["profiles"]
    assert "gemma4-e2b" in updated["profiles"]
