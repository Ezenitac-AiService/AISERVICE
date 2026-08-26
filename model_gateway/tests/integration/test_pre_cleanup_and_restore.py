"""
tests/integration/test_pre_cleanup_and_restore.py
==============================================================================
099-fix-setup-gpu-benchmark: Pre-cleanup, fallback logging & restoration tests

Verify that:
1. _record_unsupported_fallback_profile logs [BENCHMARK WARN] and sets is_supported=False
2. setup.sh contains Pre-execution cleanup and server restoration commands
==============================================================================
"""

import os
import sys
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.benchmark_context_window import _record_unsupported_fallback_profile
from src.core.config_manager import ConfigManager


def test_fallback_profile_warning_logging(capsys, tmp_path):
    """Verify _record_unsupported_fallback_profile outputs [BENCHMARK WARN] to stderr."""
    res = _record_unsupported_fallback_profile("gemma4-12b", reason="CUDA OOM")

    captured = capsys.readouterr()
    assert "[BENCHMARK WARN]" in captured.err
    assert "gemma4-12b" in captured.err
    assert res["is_supported"] is False
    assert res["recommended_context_length"] == 2048


def test_setup_sh_cleanup_and_restore_script_presence():
    """Verify setup.sh script contains FR-006 cleanup and FR-007 auto-restoration hooks."""
    setup_path = REPO_ROOT / "scripts" / "setup.sh"
    assert setup_path.exists()
    content = setup_path.read_text(encoding="utf-8")

    assert "stop_server.sh" in content
    assert "start_server.sh" in content
    assert "[FR-006]" in content
    assert "[FR-007]" in content
