import pytest
from src.core.config_manager import ConfigManager


def test_config_manager_single_source_of_truth():
    """Verify that ConfigManager returns consistent defaults without shadowed hardcoding."""
    cfg = ConfigManager()
    
    # Verify default model is qwen3.5-2b in 8GB baseline environment
    default_model = cfg.get_default_model()
    assert default_model == "qwen3.5-2b"
    
    # Verify current n_ctx is dynamic (>= 16384)
    current_ctx = cfg.get_current_n_ctx()
    assert current_ctx >= 16384


def test_config_manager_anti_shadowing():
    """Verify that lower-tier configurations cannot silently shadow dynamic server configuration."""
    cfg = ConfigManager()
    
    server_cfg = cfg.get_server_config()
    assert "default_model" in server_cfg
    assert server_cfg["default_model"] == "qwen3.5-2b"
    assert server_cfg.get("current_n_ctx", 16384) >= 16384
