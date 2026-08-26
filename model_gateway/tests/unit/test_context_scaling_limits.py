"""
Unit tests for context window scaling limits and HTTP 400 Bad Request error handling.

Feature: 028-update-platform-network-profiles
"""

import pytest
from fastapi import HTTPException
from src.core.llama_manager import LlamaManager


def test_get_max_allowed_n_ctx():
    """Verify max allowed n_ctx: small models (2B/4B) allow 8K-16K, large models (9B/12B) cap at 4096."""
    lm = LlamaManager()

    # Small models
    assert lm.get_max_allowed_n_ctx("gemma4-e2b") >= 8192
    assert lm.get_max_allowed_n_ctx("qwen3.5-2b") >= 8192
    assert lm.get_max_allowed_n_ctx("qwen3.5-4b") >= 8192

    # Large models cap at 4096
    assert lm.get_max_allowed_n_ctx("gemma4-12b") == 4096
    assert lm.get_max_allowed_n_ctx("qwen3.5-9b") == 4096


def test_validate_requested_context_success():
    """Verify context validation passes when requested n_ctx is within bounds."""
    lm = LlamaManager()
    # 4096 is safe for gemma4-12b
    lm.validate_requested_context("gemma4-12b", requested_n_ctx=4096)


def test_validate_requested_context_exceeded():
    """Verify HTTPException 400 is raised when requested n_ctx exceeds max allowed limit."""
    lm = LlamaManager()

    with pytest.raises(HTTPException) as exc_info:
        lm.validate_requested_context("gemma4-12b", requested_n_ctx=8192)

    assert exc_info.value.status_code == 400
    detail = exc_info.value.detail
    assert detail["error"]["code"] == "context_length_exceeded"
    assert "8192" in detail["error"]["message"]
    assert "4096" in detail["error"]["message"]
