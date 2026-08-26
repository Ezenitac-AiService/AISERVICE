"""
Integration test for LangGraph Compiled StateGraph & Dynamic Branching (Spec 035 T007).
"""

import pytest
import asyncio
from oliview_core.graph_orchestrator import MultiTargetGraphOrchestrator
from oliview_core.graph_state import RagGraphState


@pytest.mark.asyncio
async def test_compiled_stategraph_initialization():
    orchestrator = MultiTargetGraphOrchestrator()
    assert hasattr(orchestrator, "graph")
    assert orchestrator.graph is not None
    # Verify graph is compiled StateGraph
    assert hasattr(orchestrator.graph, "astream") or hasattr(orchestrator.graph, "ainvoke")


@pytest.mark.asyncio
async def test_compiled_stategraph_conditional_routing_spec():
    orchestrator = MultiTargetGraphOrchestrator()
    state: RagGraphState = {
        "trace_id": "test_tr_001",
        "query": "차앤박 앰플 vs 닥터지 크림 비교",
        "retry_count": 0,
    }
    decision = orchestrator.should_retry_search(state)
    assert decision in ("RETRY_SEARCH", "PROCEED_TO_SYNTHESIS", "FALLBACK")
