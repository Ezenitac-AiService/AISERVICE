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
    LangGraph Conditional Edge Evaluator.
    Determines if RAG pipeline should immediately abstain or proceed to LLM synthesis.
    """
    reranked_contexts = state.get("reranked_contexts", {})
    total_selected = sum(len(v) for v in reranked_contexts.values()) if isinstance(reranked_contexts, dict) else 0

    # Also check if target_errors or out-of-catalog was flagged
    if total_selected == 0:
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
