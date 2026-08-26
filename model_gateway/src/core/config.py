import os
from pathlib import Path
from typing import Optional
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


def get_hf_token() -> Optional[str]:
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

MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models")
os.makedirs(MODELS_DIR, exist_ok=True)
