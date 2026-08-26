import pytest
from src.core.config_manager import ConfigManager


def test_server_config_sota_settings():
    """T003: Test speculative decoding and structured output configuration schema."""
    config_mgr = ConfigManager()
    server_cfg = config_mgr.get_server_config()

    assert "speculative_decoding" in server_cfg
    assert "structured_output" in server_cfg
    assert server_cfg["structured_output"]["strict_json_schema"] is True


def test_model_catalog_draft_pairings():
    """T005: Test draft model availability in model catalog."""
    config_mgr = ConfigManager()
    catalog = config_mgr.get_model_catalog()

    model_ids = list(catalog.keys())
    assert "qwen3.5-4b" in model_ids
    assert "qwen3.5-2b" in model_ids
    assert "gemma4-12b" in model_ids
    assert "gemma4-e2b" in model_ids
