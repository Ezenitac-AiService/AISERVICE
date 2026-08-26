"""Unit tests for Zero-Search Hard Block to prevent fake review hallucinations (Spec 038 US2)."""
import pytest
from unittest.mock import patch, MagicMock

from oliview_core.nodes.synthesis_node import (
    synthesis_stream_node,
    get_token_stream,
    ZERO_SEARCH_TEMPLATE,
    is_zero_review_state,
)
from oliview_core.graph_state import RagGraphState, PatternType


def test_zero_search_hard_block_sync():
    """리뷰가 0건일 때 LLM 호출 없이 확정 템플릿 ZERO_SEARCH_TEMPLATE이 반환되는지 검증."""
    state: RagGraphState = {
        "query": "헤라 센슈얼 립 촉촉함과 각질부각 분석해줘",
        "pattern_type": PatternType.SINGLE_TARGET.value,
        "reranked_contexts": {},
        "target_entities": [],
        "context_text": "",
        "metrics": {},
        "bypass_cache": True,
    }

    assert is_zero_review_state(state) is True

    # synthesis_stream_node 실행
    with patch("oliview_core.nodes.synthesis_node.AiGatewayClient") as mock_client:
        result = synthesis_stream_node(state)
        # LLM client generate_stream should NOT be called with standard free-form prompt
        assert not mock_client.return_value.generate_stream.called

    response_text = result.get("response_text", "")
    assert "리뷰 데이터를 찾을 수 없습니다" in response_text or "등록된 실제 구매자 리뷰가 없습니다" in response_text
    assert "[리뷰" not in response_text


def test_zero_search_hard_block_stream():
    """스트리밍 모드에서도 0건 리뷰 시 가짜 후기 생성 없이 제로 서치 템플릿 토큰을 즉시 반환하는지 검증."""
    state: RagGraphState = {
        "query": "비존재 화장품 틴트 분석해줘",
        "pattern_type": PatternType.SINGLE_TARGET.value,
        "reranked_contexts": {},
        "target_entities": [],
        "context_text": "",
        "metrics": {},
        "bypass_cache": True,
    }

    tokens = list(get_token_stream(state))
    full_text = "".join(tokens)

    assert "리뷰 데이터를 찾을 수 없습니다" in full_text or "등록된 실제 구매자 리뷰가 없습니다" in full_text
    assert "[리뷰" not in full_text
