"""
Unit tests for context window scaling limits and HTTP 400 Bad Request error handling.

Feature: 006-model-gateway-upgrade
"""

import pytest
from fastapi import HTTPException
from src.core.llama_manager import LlamaManager


def test_get_max_allowed_n_ctx():
    """Verify max allowed n_ctx for Dual-LLM: 4B router allows >= 8K, 9B synthesis allows 32K."""
    lm = LlamaManager()

    # 4B router model
    assert lm.get_max_allowed_n_ctx("qwen3.5-4b") >= 8192

    # 9B synthesis model native 32K support
    assert lm.get_max_allowed_n_ctx("qwen3.5-9b") >= 32768


def test_validate_requested_context_success():
    """Verify context validation passes when requested n_ctx is within 32K bounds."""
    lm = LlamaManager()
    # 32768 is native and safe for qwen3.5-9b
    lm.validate_requested_context("qwen3.5-9b", requested_n_ctx=32768)


def test_validate_requested_context_exceeded():
    """Verify HTTPException 400 is raised when requested n_ctx exceeds max allowed limit."""
    lm = LlamaManager()

    with pytest.raises(HTTPException) as exc_info:
        lm.validate_requested_context("qwen3.5-9b", requested_n_ctx=65536)

    assert exc_info.value.status_code == 400
    detail = exc_info.value.detail
    assert detail["error"]["code"] == "context_length_exceeded"
    assert "65536" in detail["error"]["message"]
    assert "32768" in detail["error"]["message"]
