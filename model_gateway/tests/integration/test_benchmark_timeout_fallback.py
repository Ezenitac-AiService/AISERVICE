import pytest
import os
import json
import asyncio
from scripts.benchmark_context_window import async_run_fine_grained_binary_search


@pytest.mark.asyncio
async def test_async_run_fine_grained_binary_search_timeout_fallback():
    """T007 [US1]: Integration test for 120s timeout and unsupported fallback behavior."""
    # Test fallback behavior when model is invalid or fails loading
    res = await async_run_fine_grained_binary_search(model_name="non_existent_invalid_model")

    assert res is not None
    assert res.get("recommended_model") == "non_existent_invalid_model"
    assert res.get("recommended_context_length") == 2048
    assert res.get("is_supported") is False

    profiles_path = "config/model_context_profiles.json"
    assert os.path.exists(profiles_path)
    with open(profiles_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    profile = data.get("profiles", {}).get("non_existent_invalid_model", {})
    assert profile.get("is_supported") is False
    assert profile.get("recommended_context_length") == 2048
