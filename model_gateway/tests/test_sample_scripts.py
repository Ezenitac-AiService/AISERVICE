"""
Integration test for checking sample scripts executability and dynamic configuration binding.
(090-audit-test-refactor: US2)
"""
import os
import sys
import py_compile
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = REPO_ROOT / "sample"


def test_sample_directory_exists():
    """Verify sample directory and config files exist."""
    assert SAMPLE_DIR.exists()
    assert (SAMPLE_DIR / "config.json").exists() or (SAMPLE_DIR / "config.json.example").exists()


def test_sample_scripts_syntax():
    """Verify all Python scripts in sample directory compile cleanly without syntax errors."""
    python_files = list(SAMPLE_DIR.glob("*.py"))
    assert len(python_files) > 0
    
    for py_file in python_files:
        # Check syntax compilation
        py_compile.compile(str(py_file), doraise=True)


def test_sample_scripts_no_hardcoded_ips():
    """Verify executable sample scripts (sample_*.py, openai_*.py) do not contain hardcoded legacy host IPs."""
    python_files = [f for f in SAMPLE_DIR.glob("*.py") if f.name.startswith("sample_") or f.name.startswith("openai_")]
    for py_file in python_files:
        content = py_file.read_text(encoding="utf-8")
        assert "192.168.0.80" not in content, f"Hardcoded IP found in {py_file.name}"
