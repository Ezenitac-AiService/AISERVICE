import json
import pytest
import os
from scripts.ensure_models import get_dynamic_required_models

def test_failure_reason_json_persistence(tmp_path):
    profile_path = tmp_path / "model_context_profiles.json"
    dummy_data = {
        "qwen3.5-9b": {
            "max_n_ctx": 0,
            "recommended_n_ctx": 0,
            "peak_vram_mb": 0,
            "tps": 0.0,
            "is_supported": False,
            "failure_reason": "KERNEL_OOM_KILLER_EXIT_137 (Process killed by Linux Kernel OOM Killer)"
        }
    }
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(dummy_data, f, indent=4)

    with open(profile_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)

    assert loaded["qwen3.5-9b"]["failure_reason"] == "KERNEL_OOM_KILLER_EXIT_137 (Process killed by Linux Kernel OOM Killer)"

def test_dynamic_required_models_resolution():
    dummy_server_config = {
        "model": "gemma4-e2b",
        "embedding_model": "bge-m3",
        "rerank_model": "bge-reranker-v2-m3"
    }
    dummy_catalog = {
        "gemma4-e2b": {"target_dir": "models/gemma4-e2b"},
        "bge-m3": {"target_dir": "models/bge-m3"},
        "bge-reranker-v2-m3": {"target_dir": "models/bge-reranker-v2-m3"}
    }
    required = get_dynamic_required_models(server_config=dummy_server_config, catalog=dummy_catalog)
    assert "gemma4-e2b" in required
    assert "bge-m3" in required
    assert "bge-reranker-v2-m3" in required
