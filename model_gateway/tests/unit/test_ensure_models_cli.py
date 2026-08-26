"""
tests/unit/test_ensure_models_cli.py
==============================================================================
Unit tests for scripts/ensure_models.py CLI options (--all, --model, --check-only)
and resolve_target_models helper function (102-catalog-full-download-cli).
==============================================================================
"""

import sys
import subprocess
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ensure_models import resolve_target_models, get_dynamic_required_models
from src.core.config_manager import ConfigManager


def test_resolve_target_models_default():
    """Verify resolve_target_models returns default dynamic required models when no flags set."""
    catalog = ConfigManager().get_model_catalog()
    result = resolve_target_models(all_flag=False, model_arg=None, catalog=catalog)
    expected = get_dynamic_required_models(catalog=catalog)
    assert result == expected


def test_resolve_target_models_all_flag():
    """Verify resolve_target_models returns all 14 catalog model IDs when all_flag=True."""
    catalog = ConfigManager().get_model_catalog()
    result = resolve_target_models(all_flag=True, model_arg=None, catalog=catalog)
    assert len(result) == len(catalog)
    assert set(result) == set(catalog.keys())
    assert "qwen3.6-27b" in result
    assert "gemma4-26b-a4b" in result
    assert "gemma4-2b-text" in result


def test_resolve_target_models_single_model():
    """Verify resolve_target_models resolves a single valid model_arg."""
    catalog = ConfigManager().get_model_catalog()
    result = resolve_target_models(all_flag=False, model_arg="qwen3.6-27b", catalog=catalog)
    assert result == ["qwen3.6-27b"]


def test_resolve_target_models_comma_separated():
    """Verify resolve_target_models resolves comma-separated model IDs."""
    catalog = ConfigManager().get_model_catalog()
    result = resolve_target_models(all_flag=False, model_arg="qwen3.6-27b, gemma4-26b-a4b", catalog=catalog)
    assert result == ["qwen3.6-27b", "gemma4-26b-a4b"]


def test_resolve_target_models_invalid_id_raises_value_error():
    """Verify resolve_target_models raises ValueError when an unknown model_id is specified."""
    catalog = ConfigManager().get_model_catalog()
    with pytest.raises(ValueError) as exc_info:
        resolve_target_models(all_flag=False, model_arg="invalid-model-xyz", catalog=catalog)
    assert "Unknown model_id: invalid-model-xyz" in str(exc_info.value)


def test_cli_mutual_exclusion_exit_code_2():
    """Verify CLI exits with exit code 2 when both --all and --model are specified."""
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "ensure_models.py"), "--all", "--model", "qwen3.6-27b"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 2
    assert "[ERROR] --all and --model options are mutually exclusive." in proc.stderr


def test_cli_invalid_model_exit_code_1():
    """Verify CLI exits with exit code 1 when an invalid model ID is specified."""
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "ensure_models.py"), "--model", "invalid-model-xyz"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 1
    assert "[ERROR] Unknown model_id: invalid-model-xyz" in proc.stderr


def test_cli_all_check_only_runs_clean():
    """Verify CLI --all --check-only runs cleanly and checks all catalog models."""
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "ensure_models.py"), "--all", "--check-only"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert "Target:" in proc.stdout


def test_cli_download_all_alias():
    """Verify CLI --download-all alias runs cleanly and checks all catalog models."""
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "ensure_models.py"), "--download-all", "--check-only"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert "Target:" in proc.stdout


def test_cli_comma_separated_models_check_only():
    """Verify CLI --model with comma-separated IDs targets specified models."""
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "ensure_models.py"), "--model", "qwen3.6-27b,gemma4-26b-a4b", "--check-only"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert "Target: 2 models" in proc.stdout


def test_ensure_all_models_function_direct():
    """Verify ensure_all_models helper function directly with check_only and all_flag."""
    from scripts.ensure_models import ensure_all_models
    res = ensure_all_models(check_only=True, all_flag=True, auto_download=False)
    assert "target_models" in res
    assert len(res["target_models"]) >= 14
    assert res["download_summary"]["total_models"] >= 14

