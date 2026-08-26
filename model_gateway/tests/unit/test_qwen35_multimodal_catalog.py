import json
from pathlib import Path


def test_qwen35_text_model_preservation():
    """Verify that existing qwen3.5-9b entry is preserved as text-only."""
    catalog_path = Path("config/model_catalog.json")
    assert catalog_path.exists(), "config/model_catalog.json must exist"

    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    assert "qwen3.5-9b" in catalog, "qwen3.5-9b must exist in catalog"
    text_entry = catalog["qwen3.5-9b"]

    assert text_entry.get("requires_mmproj") is False, "requires_mmproj must be False for qwen3.5-9b"
    assert text_entry.get("clip_filename") is None, "clip_filename must be None for text-only qwen3.5-9b"
    assert text_entry.get("clip_path") is None, "clip_path must be None for text-only qwen3.5-9b"


def test_qwen35_vision_model_entry():
    """Verify that qwen3.5-9b-vision entry exists and has valid multimodal configuration."""
    catalog_path = Path("config/model_catalog.json")
    assert catalog_path.exists(), "config/model_catalog.json must exist"

    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    assert "qwen3.5-9b-vision" in catalog, "qwen3.5-9b-vision entry must exist in catalog"
    vision_entry = catalog["qwen3.5-9b-vision"]

    assert vision_entry.get("name") == "Qwen 3.5 9B Vision"
    assert vision_entry.get("repo_id") == "unsloth/Qwen3.5-9B-GGUF"
    assert vision_entry.get("filename") == "Qwen3.5-9B-Q4_K_M.gguf"
    assert vision_entry.get("clip_filename") == "mmproj-BF16.gguf"
    assert vision_entry.get("target_dir") == "models/qwen3.5-9b-vision"
    assert vision_entry.get("model_path") == "models/qwen3.5-9b-vision/Qwen3.5-9B-Q4_K_M.gguf"
    assert vision_entry.get("clip_path") == "models/qwen3.5-9b-vision/mmproj-BF16.gguf"
    assert vision_entry.get("chat_template") == "chatml"
    assert vision_entry.get("default_n_ctx") == 4096
    assert vision_entry.get("vram_est_mb") == 9800
    assert vision_entry.get("requires_mmproj") is True, "requires_mmproj must be True for vision entry"
    assert vision_entry.get("quant_type") == "q4_k_m"
    assert vision_entry.get("size_gb") == 5.8
