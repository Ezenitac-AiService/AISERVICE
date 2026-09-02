from unittest.mock import MagicMock
import pytest


def test_citation_bounds_pruning_no_clamping_red_gate():
    """RED GATE: Asserts invalid citation tags N > K or N < 1 and their bound claims
    are removed without clamping to other valid review indexes."""
    try:
        from oliview_core.guardrail import GroundednessSanitizer  # type: ignore
        sanitizer = GroundednessSanitizer()
        raw_answer = "진정 효과가 미흡하다는 의견이 있습니다 [브링그린 리뷰 1]. 또한 보습력도 최고입니다 [브링그린 리뷰 5]."
        result = sanitizer.sanitize_text(
            raw_answer,
            valid_k=1,
            source_reviews=["진정 효과 좋은지 모르겠어요"]
        )
        assert "[브링그린 리뷰 1]" in result.sanitized_text
        assert "[브링그린 리뷰 5]" not in result.sanitized_text
        assert "[브링그린 리뷰 2]" not in result.sanitized_text  # no clamped replacement
        assert "보습력도 최고입니다" not in result.sanitized_text  # bound claim pruned
        assert result.citations_removed_count > 0
    except (ImportError, AttributeError) as exc:
        pytest.fail(f"RED GATE: GroundednessSanitizer bounds pruning not implemented: {exc}")


def test_k0_zero_search_model_no_call_red_gate():
    """RED GATE: Asserts K=0 bypasses LLM invocation completely and returns abstention response."""
    try:
        from oliview_core.nodes.synthesis_node import execute_synthesis_node  # type: ignore
        mock_llm = MagicMock()
        state = {
            "query": "가상의 제품 어때?",
            "context_reviews": [],
            "k_bound": 0
        }
        response = execute_synthesis_node(state, llm_client=mock_llm)
        mock_llm.assert_not_called()
        assert response["status"] == "abstained"
        assert response["k_bound"] == 0
        assert response["model_invoked"] is False
    except (ImportError, AttributeError) as exc:
        pytest.fail(f"RED GATE: execute_synthesis_node K=0 no-call not implemented: {exc}")
