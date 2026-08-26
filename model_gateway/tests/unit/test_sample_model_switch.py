"""Unit tests for model switch sample scripts and config SSOT (sample_04_model_switch.py & openai_04_model_switch.py).

Feature: 117-verify-sample-model-response
"""

import os
import re
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from sample.common import get_available_llm_models, load_sample_config, print_performance_summary


def test_get_available_llm_models_filters_non_llm_models():
    """Verify get_available_llm_models returns only LLM models, filtering embedding/reranker models."""
    mock_models_response = {
        "object": "list",
        "data": [
            {"id": "qwen3.5-4b"},
            {"id": "qwen3.5-2b"},
            {"id": "bge-m3"},
            {"id": "bge-reranker-v2-m3"}
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_models_response

    with patch("httpx.get", return_value=mock_resp):
        models = get_available_llm_models()
        assert "qwen3.5-4b" in models
        assert "qwen3.5-2b" in models
        assert "bge-m3" not in models
        assert "bge-reranker-v2-m3" not in models


def test_sample_config_benchmarks_contains_target_models():
    """Verify sample config contains benchmark profiles for target models and SSOT server candidates."""
    config = load_sample_config()
    benchmarks = config.get("model_benchmarks", {})
    candidates = config.get("server_host_candidates", [])

    assert "qwen3.5-4b" in benchmarks
    assert "qwen3.5-2b" in benchmarks
    assert "http://10.0.0.41" in candidates
    assert "http://192.168.0.175" in candidates
    assert "http://127.0.0.1" in candidates


def test_print_performance_summary_model_parity_validation():
    """FR-001 & SC-004: Verify print_performance_summary correctly flags model parity match and mismatch."""
    # Test matching models
    res_match = print_performance_summary(
        "test_mode",
        t_start=1.0,
        t_end=2.0,
        gen_tokens=10,
        requested_model="qwen3.5-4b",
        responded_model="qwen3.5-4b"
    )
    assert res_match["is_model_matched"] is True
    assert res_match["requested_model"] == "qwen3.5-4b"
    assert res_match["responded_model"] == "qwen3.5-4b"

    # Test mismatching models
    res_mismatch = print_performance_summary(
        "test_mode",
        t_start=1.0,
        t_end=2.0,
        gen_tokens=10,
        requested_model="qwen3.5-4b",
        responded_model="gemma4-e4b"
    )
    assert res_mismatch["is_model_matched"] is False


def test_sample_python_files_have_zero_hardcoded_ips():
    """FR-007 & SC-002: Verify sample/ python source files do not contain hardcoded IP literals."""
    sample_dir = Path("sample")
    ip_pattern = re.compile(r'["\']http://(?:192\.168\.0\.\d+|10\.0\.0\.\d+|127\.0\.0\.1)["\']')

    violations = []
    for py_file in sample_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for line_num, line in enumerate(content.splitlines(), start=1):
            # Ignore comments
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if ip_pattern.search(line):
                violations.append(f"{py_file.name}:L{line_num}: {line.strip()}")

    assert len(violations) == 0, f"Found hardcoded IP literals in sample/ python files: {violations}"
