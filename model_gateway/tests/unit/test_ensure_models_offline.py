"""
Unit tests for ensure_models.py CLI and offline verification.

Feature: 006-model-gateway-upgrade (User Story 2)
"""

import sys
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ensure_models import get_dynamic_required_models, resolve_target_models
from src.core.config_manager import ConfigManager


def test_dynamic_required_models_includes_dual_llms():
    """Verify that get_dynamic_required_models includes qwen3.5-9b and qwen3.5-4b."""
    catalog = ConfigManager().get_model_catalog()
    required = get_dynamic_required_models(catalog=catalog)

    # 9B synthesis and 4B router must be required
    assert "qwen3.5-9b" in required
    assert "qwen3.5-4b" in required
    # bge-m3 and bge-reranker-v2-m3 must also be included
    assert "bge-m3" in required
    assert "bge-reranker-v2-m3" in required


def test_resolve_target_models_default_targets_9b():
    """Verify default target models include qwen3.5-9b as the primary synthesis LLM."""
    catalog = ConfigManager().get_model_catalog()
    targets = resolve_target_models(all_flag=False, model_arg=None, catalog=catalog)
    assert "qwen3.5-9b" in targets
