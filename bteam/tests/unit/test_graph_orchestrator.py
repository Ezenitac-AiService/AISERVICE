"""
Unit tests for MultiTargetGraphOrchestrator fast abstention on low-confidence plateau.
Feature: 008-bteam-rag-refactor (T026-A / T026-B)
Validates:
1. stream_rag() yields ABSTENTION step and ZERO_SEARCH_TEMPLATE tokens, halting immediately
   when reranked_contexts has a low-confidence plateau (max(s) < 0.50 and max(s) - min(s) < 0.10).
2. astream_rag() behaves identically in async streaming mode.
3. LLM synthesis is never invoked when low-confidence plateau abstention triggers.
"""

import pytest
from oliview_core.graph_orchestrator import MultiTargetGraphOrchestrator
from oliview_core.guardrail import ZERO_SEARCH_TEMPLATE


def test_stream_rag_abstains_on_low_confidence_plateau(mocker):
    """
    T026-A Red Gate:
    In stream_rag(), when reranked_contexts has a low-confidence plateau
    (max(s) < 0.50 and max(s) - min(s) < 0.10, e.g. [0.42, 0.39]),
    the orchestrator must yield ABSTENTION step event and ZERO_SEARCH_TEMPLATE token events,
    and immediately halt without proceeding to LLM synthesis.
    """
    mocker.patch(
        "oliview_core.graph_orchestrator.search_single_target",
        return_value={
            "search_pools": {
                "target_1": [
                    {"doc_id": "d1", "product_name": "테스트 앰플", "clean_text": "보통이에요"},
                    {"doc_id": "d2", "product_name": "테스트 앰플", "clean_text": "그냥 그래요"},
                ]
            },
            "target_errors": {},
        },
    )
    mocker.patch(
        "oliview_core.graph_orchestrator.reranker_node",
        return_value={
            "reranked_contexts": {
                "target_1": [
                    {"review_id": 1, "rerank_score": 0.42, "clean_text": "보통이에요", "rating": 3},
                    {"review_id": 2, "rerank_score": 0.39, "clean_text": "그냥 그래요", "rating": 3},
                ]
            }
        },
    )
    mock_synthesis = mocker.patch("oliview_core.graph_orchestrator.get_token_stream")

    orchestrator = MultiTargetGraphOrchestrator()
    events = list(orchestrator.stream_rag(query="테스트 앰플 어때?", session_id="test_sess"))

    # Assert ABSTENTION step event was yielded
    step_events = [e for e in events if e.get("event_type") == "step_update"]
    step_node_ids = [e.get("node_id") for e in step_events]
    assert "ABSTENTION" in step_node_ids, f"ABSTENTION not found in step nodes: {step_node_ids}"
    assert "LLM_SYNTHESIS" not in step_node_ids, "LLM_SYNTHESIS was unexpectedly reached"

    # Assert LLM synthesis was never called
    assert mock_synthesis.call_count == 0, "LLM synthesis was called despite low confidence plateau"

    # Assert ZERO_SEARCH_TEMPLATE tokens were streamed
    token_events = [e for e in events if e.get("event_type") == "token"]
    streamed_text = "".join(e.get("token", "") for e in token_events)
    assert "죄송합니다" in streamed_text or "찾지 못했습니다" in streamed_text

    # Assert pipeline completion event
    complete_events = [e for e in events if e.get("event_type") == "complete"]
    assert len(complete_events) == 1
    assert complete_events[0].get("selected_review_count") == 0


@pytest.mark.asyncio
async def test_astream_rag_abstains_on_low_confidence_plateau(mocker):
    """
    T026-A Red Gate:
    In astream_rag(), when reranked_contexts has a low-confidence plateau
    (max(s) < 0.50 and max(s) - min(s) < 0.10, e.g. [0.42, 0.39]),
    the orchestrator must yield ABSTENTION step event and ZERO_SEARCH_TEMPLATE token events,
    and immediately halt without proceeding to LLM synthesis.
    """
    mocker.patch(
        "oliview_core.graph_orchestrator.search_single_target",
        return_value={
            "search_pools": {
                "target_1": [
                    {"doc_id": "d1", "product_name": "테스트 앰플", "clean_text": "보통이에요"},
                    {"doc_id": "d2", "product_name": "테스트 앰플", "clean_text": "그냥 그래요"},
                ]
            },
            "target_errors": {},
        },
    )
    mocker.patch(
        "oliview_core.graph_orchestrator.reranker_node",
        return_value={
            "reranked_contexts": {
                "target_1": [
                    {"review_id": 1, "rerank_score": 0.42, "clean_text": "보통이에요", "rating": 3},
                    {"review_id": 2, "rerank_score": 0.39, "clean_text": "그냥 그래요", "rating": 3},
                ]
            }
        },
    )
    mock_asynthesis = mocker.patch("oliview_core.graph_orchestrator.aget_token_stream")

    orchestrator = MultiTargetGraphOrchestrator()
    events = []
    async for event in orchestrator.astream_rag(query="테스트 앰플 어때?", session_id="test_sess"):
        events.append(event)

    # Assert ABSTENTION step event was yielded
    step_events = [e for e in events if e.get("event_type") == "step_update"]
    step_node_ids = [e.get("node_id") for e in step_events]
    assert "ABSTENTION" in step_node_ids, f"ABSTENTION not found in step nodes: {step_node_ids}"
    assert "LLM_SYNTHESIS" not in step_node_ids, "LLM_SYNTHESIS was unexpectedly reached"

    # Assert LLM async synthesis was never called
    assert mock_asynthesis.call_count == 0, "LLM async synthesis was called despite low confidence plateau"

    # Assert ZERO_SEARCH_TEMPLATE tokens were streamed
    token_events = [e for e in events if e.get("event_type") == "token"]
    streamed_text = "".join(e.get("token", "") for e in token_events)
    assert "죄송합니다" in streamed_text or "찾지 못했습니다" in streamed_text

    # Assert pipeline completion event
    complete_events = [e for e in events if e.get("event_type") == "complete"]
    assert len(complete_events) == 1
    assert complete_events[0].get("selected_review_count") == 0
