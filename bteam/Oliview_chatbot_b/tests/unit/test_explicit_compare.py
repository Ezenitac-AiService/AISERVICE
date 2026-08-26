"""
Unit Tests for Explicit Compare Pattern (Spec 030 US1 T011).
2개 제품 병렬 분할 검색 및 통합 배치 리랭킹 계약 테스트.
"""
import sys, os, pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from oliview_core.graph_state import RagGraphState, PatternType, TargetEntity, TargetType
from oliview_core.nodes.router_node import intent_router_node


class TestExplicitComparePattern:
    def test_two_brand_compare_detected(self):
        """2개 브랜드 비교 패턴 감지."""
        state = RagGraphState(query="차앤박 앰플이랑 헤라 쿠션 비교해줘", trace_id="test")
        result = intent_router_node(state)
        assert result["pattern_type"] == PatternType.EXPLICIT_COMPARE.value
        assert len(result["target_entities"]) == 2

    def test_alias_resolved_in_compare(self):
        """영문 별칭이 비교 질의에서 정상 해소."""
        state = RagGraphState(query="CNP 앰플이랑 Dr.G 크림 비교해줘", trace_id="test")
        result = intent_router_node(state)
        assert result["pattern_type"] == PatternType.EXPLICIT_COMPARE.value
        brands = [t["brand_name"] for t in result["target_entities"]]
        assert "차앤박" in brands
        assert "닥터지" in brands

    def test_single_brand_not_compare(self):
        """단일 브랜드는 비교 패턴이 아님."""
        state = RagGraphState(query="차앤박 앰플 어때?", trace_id="test")
        result = intent_router_node(state)
        assert result["pattern_type"] != PatternType.EXPLICIT_COMPARE.value
        assert len(result["target_entities"]) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
