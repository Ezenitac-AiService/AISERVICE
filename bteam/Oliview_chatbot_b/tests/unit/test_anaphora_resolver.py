"""
Unit Tests for Anaphora Resolution (Spec 030 US2 T019).
멀티턴 대명사("그거", "전자", "후자") 엔티티 해소 단위 테스트.
"""
import sys, os, pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from oliview_core.anaphora_resolver import ConversationalEntityResolver
from oliview_core.session import RedisSessionStore


class TestAnaphoraResolver:
    def setup_method(self):
        """테스트용 인메모리 세션 스토어."""
        self.store = RedisSessionStore(host="invalid_host_test", port=9999, socket_timeout=0.01)
        self.resolver = ConversationalEntityResolver()
        # 세션 스토어를 모킹 대체
        import oliview_core.anaphora_resolver as mod
        self._orig_store = mod.session_store
        mod.session_store = self.store

    def teardown_method(self):
        import oliview_core.anaphora_resolver as mod
        mod.session_store = self._orig_store

    def test_proximal_resolution(self):
        """'그거' → 직전 턴의 브랜드로 해소."""
        self.store.append_message("sess1", "user", "차앤박 앰플 어때?")
        self.store.append_message("sess1", "assistant", "차앤박 프로폴리스 앰플은...")
        resolved, entities = self.resolver.resolve("그거랑 식물나라 토너 비교해줘", "sess1")
        assert "차앤박" in resolved or len(entities) > 0

    def test_no_anaphora_passthrough(self):
        """대명사 없으면 원본 질의 그대로 반환."""
        resolved, entities = self.resolver.resolve("차앤박 앰플 어때?", "sess1")
        assert resolved == "차앤박 앰플 어때?"
        assert entities == []

    def test_empty_session_graceful(self):
        """빈 세션에서 대명사 사용 시 원본 반환."""
        resolved, entities = self.resolver.resolve("그거 알려줘", "empty_session")
        assert "그거" in resolved  # 해소 실패 시 원본 유지
        assert entities == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
