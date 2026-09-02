"""
Unit and integration regression tests for Feature 045 (B-Team DB Schema, Reranker Safe Fallback & SSE Token Streaming).
"""

import os
import sys
import json
from unittest.mock import MagicMock, patch

current_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.abspath(os.path.join(current_dir, ".."))
bteam_dir = os.path.abspath(os.path.join(app_dir, ".."))
for p in [app_dir, bteam_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

from oliview_core.rerank import BGEReranker
from oliview_core.db import fetch_review_metadata
from oliview_core.client import AiGatewayClient


def test_bteam_reranker_none_safe_fallback():
    """FR-002 / SC-004: Verify BGEReranker handles client.rerank returning None without TypeError or hanging."""
    mock_client = MagicMock()
    mock_client.rerank.return_value = None  # Simulate remote gateway timeout/refusal
    
    reranker = BGEReranker(client=mock_client)
    docs = ["촉촉한 수분 크림입니다.", "지성 피부용 클렌징 폼", "향이 좋은 미스트"]
    
    ranked_indices, scores, fallback_used = reranker.rerank(
        query="수분 크림 추천",
        documents=docs,
        top_k=2
    )
    
    assert fallback_used is True, "Fallback should be marked as True"
    assert len(ranked_indices) == 2, f"Expected 2 ranked indices, got {len(ranked_indices)}"
    assert len(scores) == 2, f"Expected 2 scores, got {len(scores)}"
    assert ranked_indices == [0, 1], f"Expected indices [0, 1], got {ranked_indices}"


def test_bteam_db_fetch_review_metadata_no_brand_column_error():
    """FR-001 / SC-002: Verify fetch_review_metadata queries vw_chroma_review_sentences without p.brand."""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [
        {
            "review_id": 1,
            "product_id": 100,
            "product_name": "브링그린 클렌징 오일",
            "brand": "브링그린",
            "category": "클렌징",
            "product_url": "http://example.com/img.jpg",
            "review_clean_text": "모공 세정력이 좋아요",
            "review_text": "모공 세정력이 좋아요",
            "sentiment": "POSITIVE"
        }
    ]

    with patch("oliview_core.db.get_db_cursor") as mock_get_cursor:
        mock_get_cursor.return_value.__enter__.return_value = mock_cursor
        res = fetch_review_metadata([1])
        
        assert len(res) == 1
        assert res[1]["brand"] == "브링그린"
        assert res[1]["product_name"] == "브링그린 클렌징 오일"
        
        # Verify SQL executed mentions vw_chroma_review_sentences and not p.brand
        executed_sql = mock_cursor.execute.call_args[0][0]
        assert "vw_chroma_review_sentences" in executed_sql
        assert "p.brand," not in executed_sql


def test_ai_gateway_client_generate_stream_sse_mock():
    """SC-001 / Constitution II: Verify generate_stream yields tokens using httpx without NameError."""
    client = AiGatewayClient()

    sse_lines = [
        ': keepalive\n',
        'data: {"choices": [{"delta": {"content": "안녕하세요 "}}]}\n',
        'data: {"choices": [{"delta": {"content": "올리뷰입니다."}}]}\n',
        'data: [DONE]\n'
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_lines.return_value = sse_lines

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__enter__.return_value = mock_resp
    mock_stream_ctx.__exit__.return_value = None

    mock_httpx_client = MagicMock()
    mock_httpx_client.stream.return_value = mock_stream_ctx
    mock_httpx_client.__enter__.return_value = mock_httpx_client
    mock_httpx_client.__exit__.return_value = None

    with patch("httpx.Client", return_value=mock_httpx_client):
        tokens = list(client.generate_stream(prompt="테스트 질의", system_prompt="테스트 시스템"))

    assert len(tokens) == 2
    assert "".join(tokens) == "안녕하세요 올리뷰입니다."


def test_ai_gateway_client_generate_stream_error_fallback():
    """SC-001: Verify generate_stream yields safe error token on connection failure."""
    client = AiGatewayClient()

    with patch("httpx.Client", side_effect=Exception("Connection refused")):
        tokens = list(client.generate_stream(prompt="테스트 질의"))

    assert len(tokens) == 1
    assert "답변 생성 오류" in tokens[0]


if __name__ == "__main__":
    test_bteam_reranker_none_safe_fallback()
    test_bteam_db_fetch_review_metadata_no_brand_column_error()
    test_ai_gateway_client_generate_stream_sse_mock()
    test_ai_gateway_client_generate_stream_error_fallback()
    print("All B-Team RAG recovery unit tests passed successfully!")
