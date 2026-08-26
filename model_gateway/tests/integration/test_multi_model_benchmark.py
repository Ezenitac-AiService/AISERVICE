import pytest
import os
import json
from scripts.benchmark_context_window import evaluate_all_catalog_models, get_candidate_llm_models
from src.core.config_manager import ConfigManager


@pytest.mark.asyncio
async def test_evaluate_all_catalog_models_multi_model():
    """T006 [US1]: Integration test for multi-model real GPU benchmark execution."""
    llm_models = get_candidate_llm_models()
    assert len(llm_models) >= 2, f"Expected at least 2 LLM models in catalog, got {llm_models}"

    res = evaluate_all_catalog_models(force=True)
    assert res is not None
    assert "evaluated_models" in res
    assert len(res["evaluated_models"]) >= len(llm_models)

    # Check profiles file updated
    profiles_path = "config/model_context_profiles.json"
    assert os.path.exists(profiles_path)
    with open(profiles_path, "r", encoding="utf-8") as f:
        profiles_data = json.load(f)

    for m_id in llm_models:
        assert m_id in profiles_data.get("profiles", {}), f"Model {m_id} missing in profiles cache!"
