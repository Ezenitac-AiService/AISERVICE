# tests/test_ui_streamlit_flow.py
"""
올리챗 A Streamlit 상태 전이 및 스트리밍 플로우 검증 단위 테스트
"""

import sys
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "bteam" / "Oliview_chatbot_a"))

from common.step_callback import (
    PipelinePhase,
    StepEvent,
    ReferenceReview,
    RagExecutionMetadata,
    FallbackRecommendation,
)


class MockStatusBox:
    """Streamlit st.status Mock 객체"""

    def __init__(self, label: str = "진행 중...", expanded: bool = True):
        self.label = label
        self.expanded = expanded
        self.state = "running"
        self.written_lines = []

    def update(self, label: str = None, state: str = None, expanded: bool = None):
        if label is not None:
            self.label = label
        if state is not None:
            self.state = state
        if expanded is not None:
            self.expanded = expanded

    def write(self, text: str):
        self.written_lines.append(text)


class StreamlitStepCallbackTestImpl:
    """06.app.py 내의 StreamlitStepCallback 동작 검증용 구현체"""

    def __init__(self, status_box: MockStatusBox):
        self.status = status_box
        self.completed_metadata = None
        self.error_event = None
        self.recommendation = None

    def on_step(self, event: StepEvent):
        self.status.update(label=event.label, state="running")
        self.status.write(f"- {event.label}")

    def on_token(self, token: str):
        pass

    def on_complete(self, metadata: RagExecutionMetadata):
        self.completed_metadata = metadata
        summary_label = f"✅ 리뷰 종합 분석 완료 ({metadata.total_latency_sec:.1f}초, {metadata.selected_review_count}건 참조)"
        self.status.update(label=summary_label, state="complete", expanded=False)

    def on_error(self, error_event: StepEvent, recommendation: FallbackRecommendation = None):
        self.error_event = error_event
        self.recommendation = recommendation
        self.status.update(label=error_event.label, state="error", expanded=True)


def test_streamlit_status_transition():
    """Streamlit status 컨테이너의 4단계 수명주기 및 축약 상태 전이 검증"""
    mock_status = MockStatusBox(label="초기화 중...", expanded=True)
    cb = StreamlitStepCallbackTestImpl(mock_status)

    # 1. 의도 분석
    cb.on_step(StepEvent(PipelinePhase.INTENT_ANALYSIS, "🔍 의도 분석 중", "running", 0.1, 25))
    assert mock_status.label == "🔍 의도 분석 중"
    assert mock_status.state == "running"
    assert mock_status.expanded is True

    # 2. 검색
    cb.on_step(StepEvent(PipelinePhase.HYBRID_SEARCH, "📚 하이브리드 검색 중", "running", 0.3, 50))
    assert mock_status.label == "📚 하이브리드 검색 중"

    # 3. 리랭킹
    cb.on_step(StepEvent(PipelinePhase.RERANKING, "⚖️ 리랭킹 중", "running", 0.6, 75))
    assert mock_status.label == "⚖️ 리랭킹 중"

    # 4. LLM 생성
    cb.on_step(StepEvent(PipelinePhase.LLM_SYNTHESIS, "🧠 LLM 답변 생성 중", "running", 0.9, 90))
    assert mock_status.label == "🧠 LLM 답변 생성 중"

    # 5. 완료 -> 자동 축약 (expanded=False)
    meta = RagExecutionMetadata(
        total_latency_sec=1.5,
        searched_review_count=30,
        selected_review_count=5,
        model_used="qwen3.5-4b",
    )
    cb.on_complete(meta)

    assert mock_status.state == "complete"
    assert mock_status.expanded is False
    assert "1.5초" in mock_status.label
    assert "5건 참조" in mock_status.label
    assert len(mock_status.written_lines) == 4


def test_streamlit_status_error_handling():
    """오류 발생 시 status 박스가 error 상태 및 expanded=True로 유지되는지 검증"""
    mock_status = MockStatusBox(label="진행 중...", expanded=True)
    cb = StreamlitStepCallbackTestImpl(mock_status)

    err = StepEvent(PipelinePhase.ERROR, "⚠️ 검색 결과 없음", "warning", 0.2, 50)
    rec = FallbackRecommendation("식물나라", ["선크림", "수분감"], "리뷰 없음")
    cb.on_error(err, rec)

    assert mock_status.state == "error"
    assert mock_status.expanded is True
    assert mock_status.label == "⚠️ 검색 결과 없음"
    assert cb.recommendation is not None
    assert cb.recommendation.suggested_chips == ["선크림", "수분감"]


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    test_streamlit_status_transition()
    test_streamlit_status_error_handling()
    print("[SUCCESS] test_ui_streamlit_flow.py: All tests passed successfully!")
