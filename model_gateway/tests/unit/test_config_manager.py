import pytest
from src.core.config_manager import ConfigManager, ServerConfig, ModelCatalogEntry


def test_pydantic_server_config_defaults():
    cfg = ServerConfig()
    assert cfg.port == 8081
    assert cfg.host == "0.0.0.0"
    assert any(sub.startswith("192.168.0.0") for sub in cfg.allowed_subnets)
    assert cfg.vram_limit_mb == 11264


def test_pydantic_server_config_invalid_port():
    with pytest.raises(ValueError):
        ServerConfig(port=90)


def test_config_manager_get_server_config():
    cm = ConfigManager()
    server_cfg = cm.get_server_config()
    assert isinstance(server_cfg, dict)
    assert "port" in server_cfg
    assert "allowed_subnets" in server_cfg
    assert server_cfg["host"] == "0.0.0.0"


def test_config_manager_get_model_catalog():
    cm = ConfigManager()
    catalog = cm.get_model_catalog()
    assert isinstance(catalog, dict)
    if "qwen3.5-4b" in catalog:
        entry = catalog["qwen3.5-4b"]
        model_entry = ModelCatalogEntry(**entry)
        assert model_entry.name == "Qwen 3.5 4B"
        assert model_entry.quant_type == "q4_k_m"


def test_config_manager_alias_resolution_and_path():
    cm = ConfigManager()
    assert cm.resolve_model_id("gemma4-2b") == "gemma4-e2b"
    assert cm.resolve_model_id("gemma4-4b") == "gemma4-e4b"
    assert cm.resolve_model_id("gemma4-e2b") == "gemma4-e2b"

    cfg = cm.get_model_config("gemma4-2b")
    assert cfg is not None
    assert cfg["name"] == "Gemma 4 E2B"
    assert cfg["target_dir"] == "models/gemma4-e2b"

    abs_path = cm.get_absolute_path("config/model_catalog.json")
    assert abs_path.endswith("config/model_catalog.json")
    assert abs_path.startswith("/")


def test_config_manager_network_detection():
    cm = ConfigManager()
    net_info = cm.get_detected_network_info()
    assert isinstance(net_info, dict)
    assert "detected_active_ips" in net_info
    assert "bind_host" in net_info
    assert net_info["bind_host"] == "0.0.0.0"


def test_config_manager_admin_secret_override(monkeypatch):
    """Verify admin_secret loading from server_config and VLLM_ADMIN_SECRET env override."""
    cm = ConfigManager()
    cm.invalidate_all_caches()
    cfg = cm.get_server_config()
    assert cfg.get("admin_secret") == "aiservice"

    monkeypatch.setenv("VLLM_ADMIN_SECRET", "custom_secret_key")
    cm.invalidate_all_caches()
    cfg_override = cm.get_server_config()
    assert cfg_override.get("admin_secret") == "custom_secret_key"

    monkeypatch.delenv("VLLM_ADMIN_SECRET", raising=False)
    cm.invalidate_all_caches()


def test_dynamic_vram_capacity_binding():
    """Verify dynamic VRAM capacity binding when vram_max_capacity_mb is null/unspecified."""
    cm = ConfigManager()
    cm.invalidate_all_caches()
    vram_mb = cm.get_vram_max_capacity_mb()
    assert isinstance(vram_mb, int)
    assert vram_mb > 0


def test_merge_and_save_model_context_profiles_atomic_preservation():
    """T009 [US2]: Verify atomic load, merge, and save preservation of model context profiles."""
    cm = ConfigManager()
    cm.invalidate_all_caches()
    
    current_data = cm.load_model_context_profiles()
    initial_profiles_count = len(current_data.get("profiles", {}))
    
    new_profile = {
        "test-dummy-model": {
            "max_context_length": 4096,
            "recommended_context_length": 4096,
            "is_supported": True
        }
    }
    
    merged = cm.merge_and_save_model_context_profiles(new_profile)
    assert "test-dummy-model" in merged["profiles"]
    assert len(merged["profiles"]) >= initial_profiles_count


