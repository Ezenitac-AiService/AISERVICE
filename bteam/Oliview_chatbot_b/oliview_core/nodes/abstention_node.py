"""
CRAG Fast-Path Zero-Search Abstention Node (Feature 039 / Spec 039).
Provides immediate, deterministic zero-search refusal and alternative recommendations in sub-second latency.
"""

import time
from typing import Dict, Any, List

from ..config import get_settings
from ..graph_state import RagGraphState, FALLBACK_LABEL
from ..guardrail import ZERO_SEARCH_TEMPLATE
from ..logger import get_logger, get_trace_id, StepTimer

logger = get_logger("oliview.node.abstention")

DEFAULT_SUGGESTED_CHIPS = ["스킨케어", "선케어", "립메이크업", "쿠션", "인기 앰플"]


def should_abstain_zero_search(state: RagGraphState) -> str:
    """
    LangGraph Conditional Edge Evaluator (T010, T015).
    Determines if RAG pipeline should immediately abstain or proceed to LLM synthesis.
    Abstains if:
    1. Total selected reviews == 0.
    2. Max rerank score < 0.35 (absolute confidence gate).
    3. Low-confidence plateau: max(s) < 0.50 and (max(s) - min(s)) < 0.10 (CRAG Ambiguous band).
    """
    reranked_contexts = state.get("reranked_contexts", {})
    all_reviews: List[Dict[str, Any]] = []
    if isinstance(reranked_contexts, dict):
        for reviews in reranked_contexts.values():
            if isinstance(reviews, list):
                all_reviews.extend(reviews)

    if not all_reviews:
        return "ABSTAIN_ZERO_SEARCH"

    scores = [
        float(r.get("rerank_score", r.get("score", 0.0)))
        for r in all_reviews
        if isinstance(r, dict)
    ]

    if not scores:
        return "ABSTAIN_ZERO_SEARCH"

    max_score = max(scores)
    min_score = min(scores)

    # 1) Absolute confidence gate (< 0.35)
    if max_score < 0.35:
        return "ABSTAIN_ZERO_SEARCH"

    # 2) Low-confidence plateau (max < 0.50 and spread < 0.10)
    if max_score < 0.50 and (max_score - min_score) < 0.10:
        return "ABSTAIN_ZERO_SEARCH"

    return "PROCEED_SYNTHESIS"


def zero_search_abstention_node(state: RagGraphState) -> Dict[str, Any]:
    """
    2026 CRAG Fast-Path Abstention Node.
    Executes in <0.05s, sets is_zero_review_state=True, and prepares honest zero-search template.
    """
    trace_id = state.get("trace_id", get_trace_id())
    query = state.get("query", "")
    t_start = time.perf_counter()

    with StepTimer("ZERO_SEARCH_ABSTENTION", trace_id=trace_id):
        latency_ms = (time.perf_counter() - t_start) * 1000.0

        verdict = {
            "is_zero_search": True,
            "reason": "ZERO_REVIEWS_IN_DB",
            "suggested_chips": DEFAULT_SUGGESTED_CHIPS,
            "template_text": ZERO_SEARCH_TEMPLATE,
            "latency_ms": latency_ms,
        }

        logger.info(f"[{trace_id}] CRAG Fast-Path Abstention executed in {latency_ms:.2f}ms (Bypassed LLM Synthesis).")

        return {
            "is_zero_review_state": True,
            "zero_search_verdict": verdict,
            "context_text": ZERO_SEARCH_TEMPLATE,
            "metrics": {**state.get("metrics", {}), "zero_search_abstained": True, "abstention_latency_ms": latency_ms},
        }
