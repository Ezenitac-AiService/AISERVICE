"""
Unit tests for 3-Tier Dynamic Context Harness (Spec 035 T004).
"""

import pytest
from oliview_core.config import compute_context_harness_profile, CoreSettings
from oliview_core.guardrail import PreFlightContextGuard


def test_tier1_16k_baseline_profile():
    profile = compute_context_harness_profile(16384)
    assert profile.tier_name == "16K_BASELINE"
    assert profile.total_n_ctx == 16384
    assert profile.max_input_tokens == 10000
    assert profile.reranked_per_target == 6
    assert profile.candidates_per_target == 15
    assert profile.tokens_per_target == 3500
    assert profile.max_history_turns == 15


def test_tier2_32k_standard_profile():
    profile = compute_context_harness_profile(32768)
    assert profile.tier_name == "32K_STANDARD"
    assert profile.total_n_ctx == 32768
    assert profile.max_input_tokens == 22000
    assert profile.reranked_per_target == 12
    assert profile.candidates_per_target == 20
    assert profile.tokens_per_target == 7000
    assert profile.max_history_turns == 30


def test_tier3_ultra_profile():
    profile = compute_context_harness_profile(65536)
    assert profile.tier_name == "ULTRA"
    assert profile.total_n_ctx == 65536
    assert profile.max_input_tokens == 48000
    assert profile.reranked_per_target == 20
    assert profile.candidates_per_target == 30
    assert profile.tokens_per_target == 15000
    assert profile.max_history_turns == 50


def test_preflight_context_guard_safe():
    short_context = "<context>짧은 컨텍스트</context>"
    sanitized, was_truncated = PreFlightContextGuard.validate_and_truncate(
        short_context, total_n_ctx=16384, max_output_tokens=2048
    )
    assert not was_truncated
    assert sanitized == short_context


def test_preflight_context_guard_truncation():
    # Generate large context that exceeds safe margin (16384 * 0.85 - 2048 = 11878 tokens -> ~8200 chars)
    large_context = "<context><target>" + "아주 긴 화장품 리뷰 텍스트입니다. " * 1000 + "</target></context>"
    sanitized, was_truncated = PreFlightContextGuard.validate_and_truncate(
        large_context, total_n_ctx=16384, max_output_tokens=2048
    )
    assert was_truncated
    assert len(sanitized) < len(large_context)
    assert "</context>" in sanitized
