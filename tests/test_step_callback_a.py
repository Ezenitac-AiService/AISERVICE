# tests/test_step_callback_a.py
"""
올리챗 A StepCallbackProtocol 및 단계별 수명 주기 이벤트 단위/계약 테스트
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
    StepCallbackProtocol,
)


class MockRecordingCallback:
    """테스트용 이벤트 기록 콜백 구현체"""

    def __init__(self):
        self.steps: list[StepEvent] = []
        self.tokens: list[str] = []
        self.completed_metadata: RagExecutionMetadata | None = None
        self.error_event: StepEvent | None = None
        self.error_recommendation: FallbackRecommendation | None = None

    def on_step(self, event: StepEvent) -> None:
        self.steps.append(event)

    def on_token(self, token: str) -> None:
        self.tokens.append(token)

    def on_complete(self, metadata: RagExecutionMetadata) -> None:
        self.completed_metadata = metadata

    def on_error(self, error_event: StepEvent, recommendation: FallbackRecommendation | None = None) -> None:
        self.error_event = error_event
        self.error_recommendation = recommendation


def test_step_callback_protocol_compliance():
    """Mock 콜백이 StepCallbackProtocol을 올바르게 구현하는지 검증"""
    callback = MockRecordingCallback()
    assert isinstance(callback, StepCallbackProtocol)


def test_step_event_creation():
    """StepEvent 데이터 모델 필드 및 상태 전이 검증"""
    event = StepEvent(
        phase=PipelinePhase.HYBRID_SEARCH,
        label="📚 리뷰 하이브리드 검색 중",
        status="running",
        elapsed_sec=0.25,
        progress_percent=50,
        message="20건 후보 검색 완료",
    )
    assert event.phase == PipelinePhase.HYBRID_SEARCH
    assert event.label == "📚 리뷰 하이브리드 검색 중"
    assert event.status == "running"
    assert event.elapsed_sec == 0.25
    assert event.progress_percent == 50
    assert event.message == "20건 후보 검색 완료"


def test_callback_recording_lifecycle():
    """콜백이 단계별 이벤트, 토큰 스트림, 완료 메타데이터를 순차적으로 기록하는지 검증"""
    callback = MockRecordingCallback()

    # 1. 의도 분석 단계
    callback.on_step(
        StepEvent(
            phase=PipelinePhase.INTENT_ANALYSIS,
            label="🔍 의도 분석 중",
            status="complete",
            elapsed_sec=0.1,
            progress_percent=25,
        )
    )

    # 2. 하이브리드 검색 단계
    callback.on_step(
        StepEvent(
            phase=PipelinePhase.HYBRID_SEARCH,
            label="📚 하이브리드 검색 중",
            status="complete",
            elapsed_sec=0.4,
            progress_percent=50,
        )
    )

    # 3. 리랭킹 단계
    callback.on_step(
        StepEvent(
            phase=PipelinePhase.RERANKING,
            label="⚖️ 리랭킹 중",
            status="complete",
            elapsed_sec=0.8,
            progress_percent=75,
        )
    )

    # 4. 토큰 스트리밍
    for t in ["컬러", "그램 ", "발림", "성 좋습니다."]:
        callback.on_token(t)

    # 5. 완료 메타데이터
    ref_review = ReferenceReview(
        rank=1,
        product_name="탕후루 꿀로스",
        brand_name="컬러그램",
        category="립메이크업",
        review_score=5,
        attribute_tag="발림성",
        sentiment_label="긍정",
        separated_sentence="부드럽게 발립니다.",
        rerank_score=0.95,
    )
    meta = RagExecutionMetadata(
        total_latency_sec=1.5,
        searched_review_count=15,
        selected_review_count=1,
        model_used="qwen3.5-4b",
        reference_reviews=[ref_review],
    )
    callback.on_complete(meta)

    assert len(callback.steps) == 3
    assert callback.steps[0].phase == PipelinePhase.INTENT_ANALYSIS
    assert callback.steps[1].phase == PipelinePhase.HYBRID_SEARCH
    assert callback.steps[2].phase == PipelinePhase.RERANKING
    assert "".join(callback.tokens) == "컬러그램 발림성 좋습니다."
    assert callback.completed_metadata is not None
    assert callback.completed_metadata.total_latency_sec == 1.5
    assert len(callback.completed_metadata.reference_reviews) == 1


def test_callback_error_and_fallback_recommendation():
    """0건 또는 에러 시 콜백 처리 및 복구 칩 검증"""
    callback = MockRecordingCallback()

    error_evt = StepEvent(
        phase=PipelinePhase.ERROR,
        label="⚠️ 일치하는 리뷰 없음",
        status="warning",
        elapsed_sec=0.3,
        progress_percent=50,
        message="0건 매칭",
    )
    rec = FallbackRecommendation(
        retry_query="컬러그램 꿀로스",
        suggested_chips=["컬러그램", "립메이크업", "틴트"],
        error_message="일치하는 리뷰가 없습니다.",
    )
    callback.on_error(error_evt, rec)

    assert callback.error_event is not None
    assert callback.error_event.phase == PipelinePhase.ERROR
    assert callback.error_recommendation is not None
    assert len(callback.error_recommendation.suggested_chips) == 3


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    test_step_callback_protocol_compliance()
    test_step_event_creation()
    test_callback_recording_lifecycle()
    test_callback_error_and_fallback_recommendation()
    print("[SUCCESS] test_step_callback_a.py: All 4 test cases passed successfully!")

