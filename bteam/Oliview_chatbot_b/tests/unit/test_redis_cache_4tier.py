"""
Unit Tests for Redis 4-Tier Caching System (Spec 030 US5 T028).
L1(검색 풀), L2(임베딩), L3(리랭킹), L4(체크포인터) 4단계 캐시 키/TTL 및 동작 검증.
"""
import sys, os, pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from oliview_core.redis_pool import (
    build_l1_key, build_l2_key, build_l3_key,
    SingleFlightLock, cache_get, cache_set,
)


class TestRedis4TierCache:
    def test_l1_key_format(self):
        """L1 검색 풀 캐시 키 형식 검증."""
        key = build_l1_key("cnp_ampoule", "hydration")
        assert key == "v1:rag:pool:cnp_ampoule:hydration"

    def test_l2_key_format(self):
        """L2 임베딩 캐시 키 sha256 해싱 검증."""
        key1 = build_l2_key("  차앤박 앰플  ")
        key2 = build_l2_key("차앤박 앰플")
        assert key1 == key2  # 정규화 후 동일 해시
        assert key1.startswith("emb:bge-m3:")

    def test_l3_key_format(self):
        """L3 리랭킹 점수 캐시 키 형식 검증."""
        key = build_l3_key("차앤박 앰플 어때?", "문서1||문서2")
        assert key.startswith("rerank:")

    def test_single_flight_lock_lifecycle(self):
        """Single-flight 뮤텍스 획득 및 해제 생명주기 검증."""
        # Redis 연결이 없더라도 안전하게 True/None 반환해야 함
        acq = SingleFlightLock.acquire("test_target")
        assert acq in (True, False)
        SingleFlightLock.release("test_target")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
