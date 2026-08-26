"""
Feature 039 Test Suite: Zero-Search Global Hard Block, Dynamic Catalog Indexing & Groundedness Guard.
Constitution v1.1.1 & Spec 039 Compliant.
"""

import pytest
import os
import time
from typing import Dict, Any, List

from oliview_core.config import get_settings, AppRunMode, CoreSettings
from oliview_core.graph_state import RagGraphState, RerankedReview, TargetEntity
from oliview_core.guardrail import GroundednessSanitizer, ZERO_SEARCH_TEMPLATE
from oliview_core.tools.dynamic_catalog_index import (
    DynamicCatalogIndex,
    ProductCatalogEntry,
    CategoryRecommendationCandidate,
)
from oliview_core.nodes.abstention_node import zero_search_abstention_node, should_abstain_zero_search
from oliview_core.pipeline import prepare_pipeline_stream, ZERO_SEARCH_STATIC_MESSAGE


def test_app_run_mode_configuration(monkeypatch):
    """Test Constitution Principle VI: Dynamic APP_RUN_MODE resolution and zero hardcoding."""
    # Test DEMO Mode
    monkeypatch.setenv("APP_RUN_MODE", "DEMO")
    settings_demo = CoreSettings()
    assert settings_demo.app_run_mode == AppRunMode.DEMO
    assert settings_demo.zero_search_sla_sec == 3.0
    assert settings_demo.rag_sla_sec == 20.0

    # Test PRODUCTION Mode
    monkeypatch.setenv("APP_RUN_MODE", "PRODUCTION")
    settings_prod = CoreSettings()
    assert settings_prod.app_run_mode == AppRunMode.PRODUCTION
    assert settings_prod.zero_search_sla_sec == 0.5
    assert settings_prod.rag_sla_sec == 8.0


def test_dynamic_catalog_index_filtering():
    """Test that DynamicCatalogIndex only indexes products with review_count >= 1."""
    catalog = DynamicCatalogIndex()
    # Mock raw database records
    mock_records = [
        {"product_id": 1, "product_name": "헤라 블랙 쿠션", "brand_name": "헤라", "category": "쿠션", "total_review_count": 45, "avg_rating": 4.8},
        {"product_id": 2, "product_name": "미수집 유령 립스틱", "brand_name": "안드로메다", "category": "립", "total_review_count": 0, "avg_rating": 0.0},
        {"product_id": 3, "product_name": "롬앤 블룸 인 커버핏 쿠션", "brand_name": "롬앤", "category": "쿠션", "total_review_count": 12, "avg_rating": 4.6},
        {"product_id": 4, "product_name": "리뷰없는 쿠션", "brand_name": "헤라", "category": "쿠션", "total_review_count": 0, "avg_rating": 0.0},
    ]
    catalog.load_from_records(mock_records)

    assert "헤라" in catalog.active_brands
    assert "롬앤" in catalog.active_brands
    assert "안드로메다" not in catalog.active_brands  # review_count == 0 excluded!

    cushions = catalog.get_products_by_category("쿠션")
    assert len(cushions) == 2
    cushion_names = [p.product_name for p in cushions]
    assert "헤라 블랙 쿠션" in cushion_names
    assert "롬앤 블룸 인 커버핏 쿠션" in cushion_names
    assert "리뷰없는 쿠션" not in cushion_names


def test_dynamic_catalog_aspect_lookup():
    """Test aspect-based product ranking with small sample bias defense (review_count >= 5)."""
    catalog = DynamicCatalogIndex()
    mock_aspect_records = [
        # Product with 1 review (100% positive) -> should be excluded by small sample threshold (>=5)
        {"product_id": 10, "product_name": "단발성 쿠션", "brand_name": "브랜드A", "category": "쿠션", "total_review_count": 1, "aspect_name": "수분감", "positive_ratio": 1.0, "avg_rating": 5.0},
        # Product with 50 reviews (90% positive) -> high composite score
        {"product_id": 20, "product_name": "헤라 촉촉 쿠션", "brand_name": "헤라", "category": "쿠션", "total_review_count": 50, "aspect_name": "수분감", "positive_ratio": 0.90, "avg_rating": 4.7},
        # Product with 15 reviews (85% positive) -> eligible
        {"product_id": 30, "product_name": "롬앤 베어워터 쿠션", "brand_name": "롬앤", "category": "쿠션", "total_review_count": 15, "aspect_name": "수분감", "positive_ratio": 0.85, "avg_rating": 4.5},
    ]
    candidates = catalog.rank_aspect_candidates(mock_aspect_records, target_aspect="수분감", min_reviews=5, top_k=2)

    assert len(candidates) == 2
    assert candidates[0].product_name == "헤라 촉촉 쿠션"
    assert candidates[1].product_name == "롬앤 베어워터 쿠션"
    assert not any(c.product_name == "단발성 쿠션" for c in candidates)


def test_groundedness_sanitizer_fictional_quote_removal():
    """Test GroundednessSanitizer removes fictional placeholders and unanchored claims."""
    sanitizer = GroundednessSanitizer()

    fictional_text = """
### 1. 속건조 피부 앰플 분석
* 실제 사용자 후기: "속건조 피부에 이 앰플을 쓰니 아침마다 얼굴이 촉촉하게 느껴집니다." - *사용자 A*
* 분석: 수분 함량이 높습니다.
* 실제 사용자 후기: "하루 종일 당김 없이 흡수 잘됩니다." - *사용자 B*
* 검증된 리뷰: "차앤박 프로폴리스 앰플 흡수력 최고입니다." [차앤박 프로폴리스 앰플 리뷰 1]
"""
    result = sanitizer.sanitize_markdown(fictional_text)
    
    assert "사용자 A" not in result.cleaned_markdown
    assert "사용자 B" not in result.cleaned_markdown
    assert "[차앤박 프로폴리스 앰플 리뷰 1]" in result.cleaned_markdown
    assert result.has_violations is True
    assert len(result.removed_fictional_quotes) >= 2


def test_zero_search_crag_abstention_edge():
    """Test CRAG evaluator edge: total_selected == 0 transitions to abstention node."""
    # Case 1: Zero reviews -> ABSTAIN
    state_empty: RagGraphState = {
        "trace_id": "test_trace_1",
        "reranked_contexts": {},
        "target_entities": [{"target_id": "t1", "target_name": "알수없는상품", "target_type": "PRODUCT"}],
    }
    decision_empty = should_abstain_zero_search(state_empty)
    assert decision_empty == "ABSTAIN_ZERO_SEARCH"

    # Case 2: 1+ reviews -> PROCEED_SYNTHESIS
    state_valid: RagGraphState = {
        "trace_id": "test_trace_2",
        "reranked_contexts": {"t1": [{"doc_id": "d1", "review_text": "좋아요", "rerank_score": 0.85, "rank": 1}]},
        "target_entities": [{"target_id": "t1", "target_name": "헤라 블랙 쿠션", "target_type": "PRODUCT"}],
    }
    decision_valid = should_abstain_zero_search(state_valid)
    assert decision_valid == "PROCEED_SYNTHESIS"


def test_abstention_node_execution():
    """Test zero_search_abstention_node outputs ZERO_SEARCH_TEMPLATE and chips in sub-second."""
    t_start = time.perf_counter()
    state: RagGraphState = {
        "trace_id": "test_trace_abstain",
        "query": "화성인 안드로메다 수분크림 추천해줘",
        "reranked_contexts": {},
        "target_entities": [],
    }
    update = zero_search_abstention_node(state)
    elapsed = (time.perf_counter() - t_start) * 1000.0

    assert update["is_zero_review_state"] is True
    assert "ZERO_SEARCH_TEMPLATE" in update or "죄송합니다" in update.get("context_text", "") or "일치하는" in update.get("context_text", "")
    assert elapsed <= 50.0  # Sub-50ms execution
    assert len(update["zero_search_verdict"]["suggested_chips"]) >= 2


def test_pipeline_zero_search_hard_block(monkeypatch):
    """Test ChatA legacy pipeline.py zero search hard block prevents LLM invocation."""
    from oliview_core.pipeline import get_pipeline
    pipeline = get_pipeline()
    # Mock retriever to return 0 candidates
    monkeypatch.setattr(pipeline.retriever, "search", lambda *args, **kwargs: [])

    t_start = time.perf_counter()
    stream_gen, meta = pipeline.prepare_pipeline_stream("화성인 안드로메다 수분크림 추천해줘")
    elapsed = (time.perf_counter() - t_start) * 1000.0

    full_text = "".join(list(stream_gen))

    assert "사용자 A" not in full_text
    assert "사용자 B" not in full_text
    assert "죄송합니다" in full_text
    assert meta.selected_review_count == 0
    assert len(meta.reference_reviews) == 0
