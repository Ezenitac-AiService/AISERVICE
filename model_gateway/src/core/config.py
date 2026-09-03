import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

try:
    from pydantic import BaseModel
except ImportError:
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

try:
    from src.core.config_manager import ConfigManager
except ImportError:
    class ConfigManager:
        def get_model_catalog(self):
            return {}


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
        clamp_vram_safety_limit,
        get_model_vram_budget,
        get_runtime_fallback_chain,
        get_runtime_profile,
    )
except ImportError:
    def get_model_vram_budget() -> dict[str, int]:
        return {"llm": 2600, "embedding": 1200, "reranker": 1200}

    def clamp_vram_safety_limit(value) -> int:
        try:
            return max(0, min(int(value), 5000))
        except (TypeError, ValueError):
            return 5000

    def get_runtime_fallback_chain() -> list[str]:
        return ["vllm", "llama.cpp-cuda", "llama.cpp-cpu-openblas"]

    def get_runtime_profile() -> dict:
        return {}

_RUNTIME_PROFILE = get_runtime_profile()
VRAM_SAFETY_LIMIT_MB = clamp_vram_safety_limit(
    os.environ.get(
        "VRAM_SAFETY_LIMIT_MB", _RUNTIME_PROFILE.get("vram_safety_limit_mb", "5000")
    )
)
MODEL_VRAM_BUDGET_MB = get_model_vram_budget()
RUNTIME_FALLBACK_CHAIN = get_runtime_fallback_chain()

MODELS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models"
)
os.makedirs(MODELS_DIR, exist_ok=True)


def get_model_routing_config() -> dict[str, str]:
    """Return the SSOT routing keys mapping to model IDs."""
    return {
        "DEFAULT_MODEL": os.environ.get("DEFAULT_MODEL", "qwen3.5-4b"),
        "FAST_LLM_MODEL": os.environ.get("FAST_LLM_MODEL", "qwen3.5-2b"),
        "SYNTHESIS_LLM_MODEL": os.environ.get("SYNTHESIS_LLM_MODEL", "qwen3.5-4b"),
        "EMBEDDING_MODEL": os.environ.get("EMBEDDING_MODEL", "bge-m3"),
        "RERANK_MODEL": os.environ.get("RERANK_MODEL", "bge-reranker-v2-m3"),
    }


def get_effective_model(alias: str, single_model_mode: bool = False) -> str:
    """Resolve alias to effective model ID with single-model mode support."""
    routing = get_model_routing_config()
    alias_lower = alias.lower()
    if single_model_mode and alias_lower in ("synthesis", "synthesis_llm_model", "fast", "fast_llm_model"):
        return routing["FAST_LLM_MODEL"]
    if alias_lower in ("fast", "fast_llm_model"):
        return routing["FAST_LLM_MODEL"]
    if alias_lower in ("synthesis", "synthesis_llm_model"):
        return routing["SYNTHESIS_LLM_MODEL"]
    if alias_lower in ("embedding", "embedding_model"):
        return routing["EMBEDDING_MODEL"]
    if alias_lower in ("rerank", "rerank_model"):
        return routing["RERANK_MODEL"]
    return routing.get(alias, routing["DEFAULT_MODEL"])
