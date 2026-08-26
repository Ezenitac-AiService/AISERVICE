"""
Unit Tests for Aspect / Pros-Cons Pattern (Spec 030 US4 T025).
장단점(긍정/부정 극성 분할) 및 다중 속성 분할 검색 테스트.
"""
import sys, os, pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from oliview_core.graph_state import RagGraphState, PatternType
from oliview_core.nodes.router_node import intent_router_node


class TestAspectProsCons:
    def test_pros_cons_pattern_detected(self):
        """'헤라 블랙쿠션 장단점 알려줘' 질의 시 ASPECT_PROS_CONS 감지."""
        state = RagGraphState(query="헤라 블랙쿠션 장단점 알려줘", trace_id="test")
        result = intent_router_node(state)
        assert result["pattern_type"] == PatternType.ASPECT_PROS_CONS.value

    def test_honest_review_pattern_detected(self):
        """'솔직 후기 분석' 질의 시 ASPECT_PROS_CONS 감지."""
        state = RagGraphState(query="차앤박 프로폴리스 앰플 솔직 후기 분석해줘", trace_id="test")
        result = intent_router_node(state)
        assert result["pattern_type"] == PatternType.ASPECT_PROS_CONS.value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
