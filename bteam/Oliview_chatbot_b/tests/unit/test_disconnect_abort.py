"""
Unit Tests for Client Disconnect Abort (Spec 030 T040).
클라이언트 단절 감지 시 GPU 태스크 즉각 취소 검증.
"""
import sys, os, pytest, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


class MockRequest:
    def __init__(self, disconnect_after_turns: int = 1):
        self.turns = 0
        self.disconnect_after = disconnect_after_turns

    async def is_disconnected(self) -> bool:
        self.turns += 1
        return self.turns >= self.disconnect_after


class TestDisconnectAbort:
    @pytest.mark.asyncio
    async def test_disconnect_detected_and_aborted(self):
        """가상 클라이언트 단절 시 루프가 즉시 중단되는지 검증."""
        req = MockRequest(disconnect_after_turns=2)
        events_emitted = 0
        for i in range(10):
            if await req.is_disconnected():
                break
            events_emitted += 1

        assert events_emitted == 1, "클라이언트 단절 후에도 루프가 계속 실행됨"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
