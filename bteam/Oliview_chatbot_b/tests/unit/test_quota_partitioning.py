"""
Unit Tests for Per-Target Quota Partitioning (Spec 030 US1 T012).
타겟별 쿼터 파티셔닝 (특정 제품 쏠림 0% 검증) 단위 테스트.
"""
import sys, os, pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from oliview_core.graph_state import CandidateReview, RagGraphState
from oliview_core.nodes.rerank_node import reranker_node


class TestQuotaPartitioning:
    def _make_state(self):
        """2개 타겟, 각 5건의 후보가 있는 테스트 상태 생성."""
        pools = {
            "target_1": [
                CandidateReview(doc_id=f"t1_{i}", review_text=f"제품A 리뷰 {i}",
                    target_id="target_1", target_name="차앤박", first_stage_score=0.9 - i*0.05,
                    rating=None, skin_type=None)
                for i in range(5)
            ],
            "target_2": [
                CandidateReview(doc_id=f"t2_{i}", review_text=f"제품B 리뷰 {i}",
                    target_id="target_2", target_name="헤라", first_stage_score=0.8 - i*0.05,
                    rating=None, skin_type=None)
                for i in range(5)
            ],
        }
        return RagGraphState(
            query="차앤박 앰플이랑 헤라 쿠션 비교해줘",
            normalized_query="차앤박 앰플이랑 헤라 쿠션 비교해줘",
            search_pools=pools,
            trace_id="test",
        )

    def test_both_targets_have_reviews(self):
        """두 타겟 모두에서 리뷰가 선별되어야 함 (쏠림 0%)."""
        state = self._make_state()
        # reranker_node는 실제 GPU 호출이 필요하므로 fallback 경로를 테스트
        # (client.rerank가 None을 반환 → 1차 유사도 기반 쿼터 선별)
        result = reranker_node(state)
        reranked = result.get("reranked_contexts", {})
        assert "target_1" in reranked, "target_1 결과 누락"
        assert "target_2" in reranked, "target_2 결과 누락"
        assert len(reranked["target_1"]) > 0, "target_1 선별 리뷰 0건"
        assert len(reranked["target_2"]) > 0, "target_2 선별 리뷰 0건"

    def test_quota_limit_per_target(self):
        """타겟당 최대 3건으로 제한되어야 함."""
        state = self._make_state()
        result = reranker_node(state)
        reranked = result.get("reranked_contexts", {})
        for tid, reviews in reranked.items():
            assert len(reviews) <= 3, f"{tid}에서 {len(reviews)}건 > 3건 쿼터 초과"

    def test_empty_pool_handled(self):
        """빈 검색 풀 처리."""
        state = RagGraphState(query="테스트", search_pools={}, trace_id="test")
        result = reranker_node(state)
        assert result["is_fallback"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
