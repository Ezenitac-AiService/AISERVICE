"""
Unit tests for Self-RAG Quality Gate & Hybrid Query Reformulation (Spec 035 T005).
"""

import pytest
from oliview_core.graph_state import (
    QualityGradeVerdict,
    HybridQueryReformulationResult,
    CandidateReview,
    RerankedReview,
)
from oliview_core.nodes.quality_grade_node import evaluate_search_quality
from oliview_core.nodes.reformulation_node import hybrid_reformulate_query


def test_quality_gate_passed():
    # Good rerank scores (>= 0.35)
    reranked_contexts = {
        "target_1": [
            {"rerank_score": 0.85, "doc_id": "d1", "target_id": "target_1", "target_name": "차앤박 앰플", "review_text": "좋아요"},
            {"rerank_score": 0.72, "doc_id": "d2", "target_id": "target_1", "target_name": "차앤박 앰플", "review_text": "추천합니다"},
        ]
    }
    verdict = evaluate_search_quality(reranked_contexts, min_threshold=0.35)
    assert verdict.status == "PASSED"
    assert verdict.average_score >= 0.75
    assert len(verdict.missing_targets) == 0


def test_quality_gate_retry_on_low_score():
    # Poor rerank scores (< 0.35)
    reranked_contexts = {
        "target_1": [
            {"rerank_score": 0.21, "doc_id": "d1", "target_id": "target_1", "target_name": "차앤박 앰플", "review_text": "별로"},
        ]
    }
    verdict = evaluate_search_quality(reranked_contexts, min_threshold=0.35)
    assert verdict.status == "RETRY_SEARCH"
    assert verdict.average_score < 0.35


def test_quality_gate_retry_on_empty():
    reranked_contexts = {"target_1": []}
    verdict = evaluate_search_quality(reranked_contexts, min_threshold=0.35)
    assert verdict.status == "RETRY_SEARCH"
    assert "target_1" in verdict.missing_targets


def test_hybrid_reformulate_query():
    query = "cnp 프로폴리스 세럼 진정 효과"
    result = hybrid_reformulate_query(query, target_names=["차앤박 프로폴리스 에너지 앰플"])
    assert isinstance(result, HybridQueryReformulationResult)
    assert len(result.merged_queries) >= 1
    assert "차앤박" in str(result.merged_queries) or "프로폴리스" in str(result.merged_queries)
