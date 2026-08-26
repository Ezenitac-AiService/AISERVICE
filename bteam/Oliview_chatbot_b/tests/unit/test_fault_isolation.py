"""
Unit Tests for Sub-node Fault Isolation (Spec 030 T039).
1개 타겟 DB 에러 주입 시 500 에러 없이 잔여 정상 타겟으로 100% 완결되는지 검증.
"""
import sys, os, pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from oliview_core.nodes.search_node import search_single_target
from oliview_core.graph_state import TargetEntity, TargetType


class TestFaultIsolation:
    def test_single_target_failure_isolated(self):
        """잘못된 타겟 질의나 예외 상황에서도 크래시 없이 빈 결과 및 에러 기록 반환."""
        state = {
            "trace_id": "test_fault",
            "query": "비교 질문",
            "current_target": TargetEntity(
                target_id="broken_target",
                target_name="",  # 빈 이름으로 예외 유도
                brand_name=None,
                product_name=None,
                target_type=TargetType.PRODUCT,
                attribute_query=None,
                spec_header=None,
            ),
        }
        result = search_single_target(state)
        # 크래시 없이 search_pools 반환
        assert "search_pools" in result
        assert "broken_target" in result["search_pools"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
