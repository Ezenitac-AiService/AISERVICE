"""
Unit Tests for Feature Discovery Pattern (Spec 030 US3 T022).
속성 기반 대표 제품 선별 및 3자 비교 오케스트레이션 테스트.
"""
import sys, os, pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from oliview_core.graph_state import RagGraphState, PatternType
from oliview_core.nodes.router_node import intent_router_node


class TestFeatureDiscovery:
    def test_feature_discovery_pattern_detected(self):
        """'속건조에 좋은 인기 앰플들 비교해줘' 질의 시 FEATURE_DISCOVERY 감지."""
        state = RagGraphState(query="속건조에 좋은 인기 앰플들 비교해줘", trace_id="test")
        result = intent_router_node(state)
        assert result["pattern_type"] == PatternType.FEATURE_DISCOVERY.value

    def test_discovery_pool_target_created(self):
        """발굴 패턴 시 discovery_pool 타겟 생성 확인."""
        state = RagGraphState(query="진정 효과 좋은 크림들 추천해줘", trace_id="test")
        result = intent_router_node(state)
        assert result["pattern_type"] == PatternType.FEATURE_DISCOVERY.value
        assert len(result["target_entities"]) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
