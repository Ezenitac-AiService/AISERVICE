"""
Unit & Integration tests for scripts/ensure_models.py (092-setup-auto-model-download).
FR-001, FR-002, FR-003, FR-004, FR-005, FR-006.
"""

import os
import sys
import subprocess
import pytest
from unittest.mock import MagicMock, patch
from src.core.model_downloader import ModelDownloader


def test_ensure_models_module_import():
    """T005: ensure_models 모듈 정상 임포트 검증."""
    import scripts.ensure_models as ensure_models
    assert hasattr(ensure_models, "ensure_all_models")
    assert hasattr(ensure_models, "REQUIRED_MODELS")
    assert "qwen3.5-4b" in ensure_models.REQUIRED_MODELS
    assert "bge-m3" in ensure_models.REQUIRED_MODELS
    assert "bge-reranker-v2-m3" in ensure_models.REQUIRED_MODELS


def test_ensure_models_check_only_mode():
    """T005: --check-only 모드 실행 검증."""
    import scripts.ensure_models as ensure_models
    with patch.object(ModelDownloader, "is_model_available", return_value=True):
        res = ensure_models.ensure_all_models(check_only=True, auto_download=False)
        assert res["all_models_present"] is True
        assert res["download_summary"]["total_models"] == 3


def test_ensure_models_smart_skip_when_present():
    """T008, T009: 이미 존재하는 경우 Smart Skip 및 빠른 반환 검증."""
    import scripts.ensure_models as ensure_models
    with patch.object(ModelDownloader, "is_model_available", return_value=True):
        res = ensure_models.ensure_all_models(check_only=False, auto_download=True)
        assert res["all_models_present"] is True
        assert res["download_summary"]["present_count"] == 3
        assert res["download_summary"]["downloaded_count"] == 0


def test_ensure_models_cli_execution():
    """T005: python scripts/ensure_models.py CLI 독립 실행 검증."""
    cmd = [sys.executable, "scripts/ensure_models.py", "--check-only"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0
    assert "PROVISIONING" in proc.stdout or "파이프라인" in proc.stdout
