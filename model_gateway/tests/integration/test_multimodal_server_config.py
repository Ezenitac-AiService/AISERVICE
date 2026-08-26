import os
import json
from pathlib import Path
from src.core.config_manager import ConfigManager
from src.core.model_downloader import ModelDownloader
from src.core.process_manager import ProcessManager
from scripts.ensure_models import resolve_target_models, get_dynamic_required_models


def test_qwen35_vision_config_integration():
    """Verify integration of qwen3.5-9b-vision across ConfigManager, ModelDownloader, ProcessManager."""
    cm = ConfigManager()
    catalog = cm.get_model_catalog()

    assert "qwen3.5-9b-vision" in catalog, "qwen3.5-9b-vision must exist in model catalog"
    entry = catalog["qwen3.5-9b-vision"]

    assert entry["requires_mmproj"] is True
    assert entry["clip_filename"] == "mmproj-BF16.gguf"
    assert entry["clip_path"] == "models/qwen3.5-9b-vision/mmproj-BF16.gguf"

    # Test ModelDownloader catalog integration
    downloader = ModelDownloader(config_manager=cm)
    dl_catalog = downloader.catalog
    assert "qwen3.5-9b-vision" in dl_catalog
    assert dl_catalog["qwen3.5-9b-vision"]["clip_filename"] == "mmproj-BF16.gguf"

    # Test ProcessManager preset integration
    pm = ProcessManager(config_manager=cm)
    assert "qwen3.5-9b-vision" in pm.model_presets
    preset = pm.model_presets["qwen3.5-9b-vision"]
    assert preset["clip"] == "models/qwen3.5-9b-vision/mmproj-BF16.gguf"
    assert preset["requires_mmproj"] is True


def test_ensure_models_target_resolution():
    """Verify resolve_target_models handles qwen3.5-9b-vision correctly."""
    cm = ConfigManager()
    catalog = cm.get_model_catalog()

    # Specific model argument
    resolved = resolve_target_models(model_arg="qwen3.5-9b-vision", catalog=catalog)
    assert resolved == ["qwen3.5-9b-vision"]

    # All flag
    resolved_all = resolve_target_models(all_flag=True, catalog=catalog)
    assert "qwen3.5-9b-vision" in resolved_all
    assert "qwen3.5-9b" in resolved_all  # Text model preserved

    # Dynamic required models with server config override
    mock_server_cfg = {"model": "qwen3.5-9b-vision", "embedding_model": "bge-m3", "rerank_model": "bge-reranker-v2-m3"}
    req = get_dynamic_required_models(server_config=mock_server_cfg, catalog=catalog)
    assert "qwen3.5-9b-vision" in req
