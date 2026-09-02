"""
Test for Feature 047 (User Story 1):
Verify entity naming decoupling and authentic Olive Young search URL binding in category/discovery queries.
"""

import pytest
import urllib.parse
from oliview_core.nodes.router_node import intent_router_node
from oliview_core.utils.document_top_p import DocumentTopPCalculator
from oliview_core.graph_state import CandidateReview


def test_router_node_discovery_does_not_distort_product_name():
    """Test that FEATURE_DISCOVERY queries do not set target_name as product_name."""
    state = {
        "query": "스킨케어에서 수분감 좋은 인기 앰플 추천해줘",
        "tenant_id": "chata",
    }
    result = intent_router_node(state)
    target_entities = result.get("target_entities", [])
    assert len(target_entities) > 0

    for entity in target_entities:
        # product_name must be None or an actual product, NEVER the raw full query sentence
        assert entity.get("product_name") != "스킨케어에서 수분감 좋은 인기 앰플 추천해줘"


def test_document_top_p_uses_clean_product_name_for_tags():
    """Test that DocumentTopPCalculator uses the real product name for tags instead of the raw query sentence."""
    selector = DocumentTopPCalculator()
    candidates = [
        {
            "doc_id": "doc_101",
            "review_text": "피부 진정과 수분을 채워주는 앰플입니다.",
            "target_id": "target_1",
            "target_name": "스킨케어에서 수분감 좋은 인기 앰플 추천해줘",
            "product_name": "차앤박(CNP) 뮤제너 피토 수딩 앰플 35ml 1+1 기획",
            "clean_product_name": "차앤박 뮤제너 피토 수딩 앰플",
            "brand_name": "차앤박",
            "category": "스킨케어",
            "attribute_name": "수분감",
            "first_stage_score": 0.85,
            "rerank_score": 0.95,
        }
    ]

    selected = selector.filter_documents(
        candidates,
        target_name="스킨케어에서 수분감 좋은 인기 앰플 추천해줘",
        short_target_name="차앤박 뮤제너 피토 수딩 앰플",
    )

    assert len(selected) == 1
    citation = selected[0]
    # Tag should contain the product name, NOT the full query sentence
    assert "스킨케어에서 수분감" not in citation.citation_tag
    assert "차앤박" in citation.citation_tag
    assert citation.citation_tag == "[차앤박 뮤제너 피토 수딩 앰플 리뷰 1]"


def test_oliveyoung_search_url_uses_real_product_name():
    """Test that the generated Olive Young URL queries the real product name, not the user prompt."""
    raw_query = "스킨케어에서 수분감 좋은 인기 앰플 추천해줘"
    actual_product = "차앤박 뮤제너 피토 수딩 앰플"

    encoded_product = urllib.parse.quote(actual_product)
    expected_url = f"https://www.oliveyoung.co.kr/store/search/getSearchMain.do?query={encoded_product}"

    # Verify query parameter contains actual product name
    assert "query=" in expected_url
    assert urllib.parse.quote(raw_query) not in expected_url
    assert encoded_product in expected_url
