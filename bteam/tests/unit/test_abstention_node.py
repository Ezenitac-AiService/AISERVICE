"""
Unit tests for CRAG/Self-RAG Fast-Path Abstention Node.
Feature: 008-bteam-rag-refactor (T010)
Validates:
1. Fast Abstention on 0 selected reviews (< 0.1s execution).
2. Abstention on low-confidence plateau (max(s) < 0.50 and max(s) - min(s) < 0.10).
3. Proceeding to synthesis when high-confidence reviews exist (e.g. s >= 0.50).
"""

import time
import pytest
from oliview_core.graph_state import RagGraphState
from oliview_core.nodes.abstention_node import (
    should_abstain_zero_search,
    zero_search_abstention_node,
)


def test_abstain_on_zero_selected_reviews():
    """Verify immediate abstention when no reviews are found in DB."""
    state: RagGraphState = {
        "trace_id": "test_abstain_001",
        "reranked_contexts": {},
    }
    decision = should_abstain_zero_search(state)
    assert decision == "ABSTAIN_ZERO_SEARCH"

    t0 = time.perf_counter()
    res = zero_search_abstention_node(state)
    elapsed = time.perf_counter() - t0

    assert elapsed < 0.1, f"Fast abstention took {elapsed:.4f}s, expected < 0.1s"
    assert res.get("is_zero_review_state") is True
    assert "zero_search_verdict" in res
    assert res["zero_search_verdict"]["is_zero_search"] is True


def test_abstain_on_low_confidence_plateau():
    """
    CRAG Ambiguous / Low-confidence plateau test:
    When candidate reviews all have low scores without discriminatory signal:
    e.g., scores = [0.42, 0.40, 0.38] (max < 0.50 and spread < 0.10)
    Pipeline should abstain to prevent hallucinations.
    """
    state: RagGraphState = {
        "trace_id": "test_abstain_002",
        "reranked_contexts": {
            "target_1": [
                {"review_id": 1, "rerank_score": 0.42, "clean_text": "보통이에요"},
                {"review_id": 2, "rerank_score": 0.40, "clean_text": "그냥 그래요"},
                {"review_id": 3, "rerank_score": 0.38, "clean_text": "무난해요"},
            ]
        },
    }
    decision = should_abstain_zero_search(state)
    assert decision == "ABSTAIN_ZERO_SEARCH"


def test_proceed_on_high_confidence_reviews():
    """
    High-confidence review presence should proceed to LLM synthesis.
    e.g. score >= 0.50
    """
    state: RagGraphState = {
        "trace_id": "test_proceed_001",
        "reranked_contexts": {
            "target_1": [
                {"review_id": 10, "rerank_score": 0.88, "clean_text": "수분감이 아주 풍부하고 흡수도 빨라요"},
                {"review_id": 11, "rerank_score": 0.74, "clean_text": "끈적임 없이 촉촉하게 흡수됩니다"},
            ]
        },
    }
    decision = should_abstain_zero_search(state)
    assert decision == "PROCEED_SYNTHESIS"
