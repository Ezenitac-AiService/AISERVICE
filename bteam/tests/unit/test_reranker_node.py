"""
Unit tests for Reranker Node:
1. Sigmoid normalization of raw logits into [0, 1].
2. Absolute confidence threshold gate (min_score_gate = 0.35).
3. 3-Guardrail Dynamic Score Cliff Truncation:
   - Guardrail 1: Minimum quota min_k = 2 preserved (no cliff cutoff before rank 2).
   - Guardrail 2: High-confidence preservation (s_{i+1} >= 0.65 exempted from cliff cutoff).
   - Guardrail 3: Max document cap max_k = 5.
Feature: 008-bteam-rag-refactor (T011)
"""

import math
import pytest
from oliview_core.nodes.rerank_node import (
    sigmoid,
    apply_3guardrail_score_cliff,
    reranker_node,
)
from oliview_core.graph_state import RagGraphState


def test_sigmoid_normalization():
    """Verify raw logits from Cross-Encoder are correctly normalized into [0, 1]."""
    assert math.isclose(sigmoid(0.0), 0.5, abs_tol=1e-5)
    assert math.isclose(sigmoid(2.197), 0.9, abs_tol=1e-2)
    assert math.isclose(sigmoid(-2.197), 0.1, abs_tol=1e-2)
    # Monotonicity
    assert sigmoid(3.0) > sigmoid(1.0) > sigmoid(-1.0)


def test_min_score_gate_filtering():
    """Verify documents below min_score_gate (0.35) are filtered out."""
    candidates = [
        {"doc_id": "d1", "rerank_score": 0.85, "review_text": "아주 좋아요"},
        {"doc_id": "d2", "rerank_score": 0.50, "review_text": "보통이에요"},
        {"doc_id": "d3", "rerank_score": 0.30, "review_text": "별로예요"},
        {"doc_id": "d4", "rerank_score": 0.15, "review_text": "최악이에요"},
    ]
    filtered = apply_3guardrail_score_cliff(candidates, min_score_gate=0.35)
    doc_ids = [d["doc_id"] for d in filtered]
    assert "d1" in doc_ids
    assert "d2" in doc_ids
    assert "d3" not in doc_ids
    assert "d4" not in doc_ids


def test_guardrail1_min_k_preservation():
    """
    Guardrail 1: min_k = 2.
    Even if cliff occurs between rank 1 and rank 2 (delta >= 0.15),
    rank 2 MUST be preserved as long as its score >= min_score_gate.
    """
    candidates = [
        {"doc_id": "d1", "rerank_score": 0.90, "review_text": "수분감 최고"},
        {"doc_id": "d2", "rerank_score": 0.70, "review_text": "흡수력 최고"}, # delta=0.20 >= 0.15
        {"doc_id": "d3", "rerank_score": 0.40, "review_text": "무난함"},    # delta=0.30 >= 0.15, s<0.65
    ]
    filtered = apply_3guardrail_score_cliff(candidates, min_score_gate=0.35, min_k=2, cliff_delta=0.15)
    doc_ids = [d["doc_id"] for d in filtered]
    # d1 and d2 must be retained due to min_k = 2
    assert "d1" in doc_ids
    assert "d2" in doc_ids
    # d3 cut off by cliff
    assert "d3" not in doc_ids
    assert len(filtered) == 2


def test_guardrail2_high_confidence_preservation():
    """
    Guardrail 2: High confidence preservation (s_{i+1} >= 0.65).
    Even if delta >= 0.15 between rank 2 and rank 3,
    if rank 3 has score >= 0.65, it MUST NOT be cut off.
    """
    candidates = [
        {"doc_id": "d1", "rerank_score": 0.95, "review_text": "1위"},
        {"doc_id": "d2", "rerank_score": 0.88, "review_text": "2위"},
        {"doc_id": "d3", "rerank_score": 0.68, "review_text": "3위"}, # delta=0.20, but score 0.68 >= 0.65!
        {"doc_id": "d4", "rerank_score": 0.45, "review_text": "4위"}, # delta=0.23, score 0.45 < 0.65 -> Cutoff!
    ]
    filtered = apply_3guardrail_score_cliff(candidates, min_score_gate=0.35, min_k=2, cliff_delta=0.15, high_conf_threshold=0.65)
    doc_ids = [d["doc_id"] for d in filtered]
    assert "d1" in doc_ids
    assert "d2" in doc_ids
    assert "d3" in doc_ids
    assert "d4" not in doc_ids
    assert len(filtered) == 3


def test_guardrail3_max_k_cap():
    """
    Guardrail 3: max_k = 5 cap.
    Even if 7 documents have score >= 0.80 without cliff, at most 5 are returned.
    """
    candidates = [
        {"doc_id": f"d{i}", "rerank_score": 0.90 - i * 0.02, "review_text": f"{i}위"}
        for i in range(10)
    ]
    filtered = apply_3guardrail_score_cliff(candidates, max_k=5)
    assert len(filtered) == 5
