"""
Unit Tests for SubStepEvent Protocol & Streaming (Spec 030 US6 T032).
SSE SubStepEvent 직렬화 및 스트리밍 이벤트 무결성 테스트.
"""
import sys, os, json, pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from oliview_core.graph_state import SubStepEvent, StepStatus, SubStepAction
from oliview_core.graph_orchestrator import _make_step_event, _make_fallback_event


class TestSubStepEvents:
    def test_step_event_structure(self):
        """기본 스텝 이벤트 직렬화 구조 검증."""
        evt = _make_step_event("req_12345", "INTENT", "1. 의도 분석", StepStatus.RUNNING)
        assert evt["trace_id"] == "req_12345"
        assert evt["event_type"] == "step_update"
        assert evt["step_id"] == "INTENT"
        assert evt["status"] == "running"
        # JSON 직렬화 가능 여부
        serialized = json.dumps(evt, ensure_ascii=False)
        assert "req_12345" in serialized

    def test_substep_detail_structure(self):
        """타겟별 서브스텝 상세 정보 포함 이벤트 직렬화 검증."""
        from oliview_core.graph_state import SubStepDetail
        sub = SubStepDetail(
            target_index=1,
            total_targets=2,
            target_id="target_1",
            target_name="차앤박 앰플",
            action=SubStepAction.SEARCH_DONE.value,
            count=10,
            message="차앤박 앰플 10건 수집 완료",
        )
        evt = _make_step_event("req_12345", "SEARCH", "2. 검색", StepStatus.COMPLETE, sub_step=sub)
        assert evt["sub_step"]["target_name"] == "차앤박 앰플"
        assert evt["sub_step"]["count"] == 10

    def test_fallback_event_structure(self):
        """폴백 알림 이벤트 구조 검증."""
        evt = _make_fallback_event("req_12345", "리랭커 5.0초 타임아웃")
        assert evt["event_type"] == "fallback_alert"
        assert evt["fallback_info"]["triggered"] is True
        assert "신속 분석" in evt["fallback_info"]["label"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
