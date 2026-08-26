"""
Feature 039 Test Suite: Zero-Search Global Hard Block, Dynamic Catalog Indexing & Groundedness Guard.
Constitution v1.1.1 & Spec 039 Compliant (ChatB Target).
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


def test_app_run_mode_configuration_b(monkeypatch):
    """Test Constitution Principle VI: Dynamic APP_RUN_MODE resolution in ChatB."""
    monkeypatch.setenv("APP_RUN_MODE", "DEMO")
    settings_demo = CoreSettings()
    assert settings_demo.app_run_mode == AppRunMode.DEMO
    assert settings_demo.zero_search_sla_sec == 3.0

    monkeypatch.setenv("APP_RUN_MODE", "PRODUCTION")
    settings_prod = CoreSettings()
    assert settings_prod.app_run_mode == AppRunMode.PRODUCTION
    assert settings_prod.zero_search_sla_sec == 0.5


def test_dynamic_catalog_index_filtering_b():
    """Test that DynamicCatalogIndex only indexes products with review_count >= 1."""
    catalog = DynamicCatalogIndex()
    mock_records = [
        {"product_id": 1, "product_name": "헤라 블랙 쿠션", "brand_name": "헤라", "category": "쿠션", "total_review_count": 45, "avg_rating": 4.8},
        {"product_id": 2, "product_name": "미수집 유령 립스틱", "brand_name": "안드로메다", "category": "립", "total_review_count": 0, "avg_rating": 0.0},
    ]
    catalog.load_from_records(mock_records)
    assert "헤라" in catalog.active_brands
    assert "안드로메다" not in catalog.active_brands


def test_groundedness_sanitizer_fictional_quote_removal_b():
    """Test GroundednessSanitizer removes fictional placeholders in ChatB."""
    sanitizer = GroundednessSanitizer()
    fictional_text = """
* 실제 사용자 후기: "속건조 피부에 이 앰플을 쓰니 아침마다 촉촉하게 느껴집니다." - *사용자 A*
* 실제 사용자 후기: "하루 종일 당김 없이 흡수 잘됩니다." - *사용자 B*
"""
    result = sanitizer.sanitize_markdown(fictional_text)
    assert "사용자 A" not in result.cleaned_markdown
    assert "사용자 B" not in result.cleaned_markdown
    assert result.has_violations is True


def test_zero_search_crag_abstention_edge_b():
    """Test CRAG evaluator edge in ChatB context."""
    state_empty: RagGraphState = {
        "trace_id": "test_trace_1_b",
        "reranked_contexts": {},
        "target_entities": [],
    }
    assert should_abstain_zero_search(state_empty) == "ABSTAIN_ZERO_SEARCH"
