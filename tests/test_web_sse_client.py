# tests/test_web_sse_client.py
"""
올리챗 B Web UI SSE 이벤트 파서 및 타임라인 상태 머신 검증 테스트
"""

import sys
import os
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


class MockWebTimelineState:
    """웹 브라우저 상의 4단계 타임라인 상태 머신 Mock"""

    def __init__(self):
        self.steps = {
            "INTENT_ANALYSIS": "idle",
            "HYBRID_SEARCH": "idle",
            "RERANKING": "idle",
            "LLM_SYNTHESIS": "idle",
        }
        self.accumulated_text = ""
        self.summary_badge = ""
        self.is_collapsed = False
        self.error_displayed = None
        self.chips = []

    def handle_sse_event(self, event_type: str, data: dict):
        if event_type == "step":
            phase = data.get("phase")
            if phase in self.steps:
                # 이전 단계들은 done으로 전환
                phases = list(self.steps.keys())
                curr_idx = phases.index(phase)
                for i in range(curr_idx):
                    self.steps[phases[i]] = "done"
                self.steps[phase] = "active"

        elif event_type == "token":
            self.accumulated_text += data.get("token", "")

        elif event_type == "complete":
            for p in self.steps:
                self.steps[p] = "done"
            sec = data.get("total_latency_sec", 0.0)
            cnt = data.get("selected_review_count", 0)
            self.summary_badge = f"✅ 리뷰 종합 분석 완료 ({sec:.1f}초, {cnt}건 참조)"
            self.is_collapsed = True

        elif event_type == "error":
            self.error_displayed = data.get("error_message")
            self.chips = data.get("suggested_chips", [])


def test_web_timeline_progression():
    """SSE step 이벤트에 따라 타임라인 상태가 순차적으로 done/active로 전환되는지 검증"""
    timeline = MockWebTimelineState()

    timeline.handle_sse_event("step", {"phase": "INTENT_ANALYSIS", "progress_percent": 25})
    assert timeline.steps["INTENT_ANALYSIS"] == "active"
    assert timeline.steps["HYBRID_SEARCH"] == "idle"

    timeline.handle_sse_event("step", {"phase": "HYBRID_SEARCH", "progress_percent": 50})
    assert timeline.steps["INTENT_ANALYSIS"] == "done"
    assert timeline.steps["HYBRID_SEARCH"] == "active"

    timeline.handle_sse_event("step", {"phase": "RERANKING", "progress_percent": 75})
    assert timeline.steps["HYBRID_SEARCH"] == "done"
    assert timeline.steps["RERANKING"] == "active"

    timeline.handle_sse_event("step", {"phase": "LLM_SYNTHESIS", "progress_percent": 90})
    assert timeline.steps["RERANKING"] == "done"
    assert timeline.steps["LLM_SYNTHESIS"] == "active"


def test_web_token_typewriter_and_completion():
    """SSE token 및 complete 이벤트 수신 시 텍스트 누적 및 배지 축약 검증"""
    timeline = MockWebTimelineState()

    # Step transition
    timeline.handle_sse_event("step", {"phase": "LLM_SYNTHESIS"})

    # Tokens
    for tok in ["컬러그램 ", "탕후루 ", "꿀로스는 ", "광택감이 ", "우수합니다."]:
        timeline.handle_sse_event("token", {"token": tok})

    assert timeline.accumulated_text == "컬러그램 탕후루 꿀로스는 광택감이 우수합니다."

    # Complete
    timeline.handle_sse_event("complete", {
        "phase": "COMPLETED",
        "total_latency_sec": 1.32,
        "selected_review_count": 3,
        "reference_reviews": []
    })

    assert timeline.is_collapsed is True
    assert "1.3초" in timeline.summary_badge
    assert "3건 참조" in timeline.summary_badge
    assert all(status == "done" for status in timeline.steps.values())


def test_web_error_and_chip_recovery():
    """SSE error 이벤트 수신 시 에러 메시지 및 추천 칩 렌더링 검증"""
    timeline = MockWebTimelineState()

    timeline.handle_sse_event("error", {
        "phase": "ERROR",
        "error_message": "검색 결과가 없습니다.",
        "suggested_chips": ["컬러그램", "식물나라", "틴트"]
    })

    assert timeline.error_displayed == "검색 결과가 없습니다."
    assert timeline.chips == ["컬러그램", "식물나라", "틴트"]


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    test_web_timeline_progression()
    test_web_token_typewriter_and_completion()
    test_web_error_and_chip_recovery()
    print("[SUCCESS] test_web_sse_client.py: All tests passed successfully!")
