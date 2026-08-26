"""Unit Tests for Category Discovery & Multi-Target Extraction (Spec 037 US2)."""
import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from oliview_core.nodes.router_node import intent_router_node
from oliview_core.graph_state import PatternType


class TestCategoryDiscovery(unittest.TestCase):

    def test_category_discovery_routing(self):
        state = {
            "query": "민감성 피부라 트러블 안나고 순하면서 붉은기 진정에 좋은 쿠션팩트 있나요",
            "session_id": "test_session_disc",
        }
        res = intent_router_node(state)

        self.assertEqual(res["pattern_type"], PatternType.FEATURE_DISCOVERY.value)
        self.assertGreater(len(res["target_entities"]), 0)
        # 각 타겟이 유효한 상품 또는 후보 풀인지 검증
        for t in res["target_entities"]:
            self.assertIsNotNone(t["target_name"])

    def test_explicit_compare_routing(self):
        state = {
            "query": "차앤박 프로폴리스 앰플이랑 토리든 다이브인 세럼 비교해줘",
            "session_id": "test_session_comp",
        }
        res = intent_router_node(state)

        self.assertEqual(res["pattern_type"], PatternType.EXPLICIT_COMPARE.value)
        self.assertGreaterEqual(len(res["target_entities"]), 2)


if __name__ == "__main__":
    unittest.main()
