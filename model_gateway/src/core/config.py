import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel
from src.core.config_manager import ConfigManager

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


class ModelConfig(BaseModel):
    model_id: str
    repo_id: str
    filename: str
    n_ctx: int = 8192


def get_hf_token() -> str | None:
    """Retrieve HF_TOKEN from environment if set (loaded via .env). Returns None if missing."""
    return os.environ.get("HF_TOKEN")


# Single Source of Truth (SSOT) derived from ConfigManager
_cm = ConfigManager()


def get_supported_models() -> dict:
    """Dynamically builds SUPPORTED_MODELS dictionary from model_catalog.json SSOT."""
    catalog = _cm.get_model_catalog()
    models = {}
    for model_id, entry in catalog.items():
        models[model_id] = ModelConfig(
            model_id=model_id,
            repo_id=entry.get("repo_id", ""),
            filename=entry.get("filename", ""),
            n_ctx=entry.get("default_n_ctx", 4096),
        )
    return models


SUPPORTED_MODELS = get_supported_models()

try:
    from src.config import (
        get_model_vram_budget,
        get_runtime_fallback_chain,
        get_runtime_profile,
    )
except ImportError:
    def get_model_vram_budget() -> dict[str, int]:
        return {"llm": 2600, "embedding": 1200, "reranker": 1200}

    def get_runtime_fallback_chain() -> list[str]:
        return ["vllm", "llama.cpp-cuda", "llama.cpp-cpu-openblas"]

    def get_runtime_profile() -> dict:
        return {}

_RUNTIME_PROFILE = get_runtime_profile()
VRAM_SAFETY_LIMIT_MB = min(
    int(
        os.environ.get(
            "VRAM_SAFETY_LIMIT_MB", _RUNTIME_PROFILE.get("vram_safety_limit_mb", "5000")
        )
    ),
    5000,
)
MODEL_VRAM_BUDGET_MB = get_model_vram_budget()
RUNTIME_FALLBACK_CHAIN = get_runtime_fallback_chain()

MODELS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models"
)
os.makedirs(MODELS_DIR, exist_ok=True)
