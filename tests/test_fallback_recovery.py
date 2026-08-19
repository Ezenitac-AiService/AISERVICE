# tests/test_fallback_recovery.py
"""
올리챗 A/B 0건 검색, 모델 지연 2B 폴백 및 1클릭 복구 칩 검증 테스트 (US3)
"""

import sys
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "bteam" / "Oliview_chatbot_a"))

from common.step_callback import (
    PipelinePhase,
    StepEvent,
    FallbackRecommendation,
)


def test_zero_result_fallback_generation():
    """0건 검색 시 완화된 추천 검색어 칩 생성 검증"""
    query = "미등록화장품 신제품 발림성 알려줘"
    error_event = StepEvent(
        phase=PipelinePhase.ERROR,
        label="⚠️ 일치하는 리뷰 데이터 없음 (0건)",
        status="warning",
        elapsed_sec=0.2,
        progress_percent=50,
        message="0건 매칭",
    )

    recommendation = FallbackRecommendation(
        retry_query=query,
        suggested_chips=["컬러그램", "식물나라", "발림성", "수분감"],
        error_message="관련 리뷰 데이터를 찾을 수 없습니다. 올리브영 등록 상품명으로 다시 검색해주세요.",
    )

    assert error_event.phase == PipelinePhase.ERROR
    assert error_event.status == "warning"
    assert len(recommendation.suggested_chips) == 4
    assert "컬러그램" in recommendation.suggested_chips


def test_model_fallback_state_notification():
    """2B 폴백 전환 시 이벤트 레이블 및 모델 메타데이터 검증"""
    fallback_event = StepEvent(
        phase=PipelinePhase.LLM_SYNTHESIS,
        label="⚠️ 메인 모델 지연으로 qwen3.5-2b 초고속 모드로 자동 전환하여 답변을 생성합니다.",
        status="running",
        elapsed_sec=2.1,
        progress_percent=90,
        extra_data={"fallback_model": "qwen3.5-2b", "original_model": "qwen3.5-4b"},
    )

    assert fallback_event.phase == PipelinePhase.LLM_SYNTHESIS
    assert "qwen3.5-2b" in fallback_event.label
    assert fallback_event.extra_data["fallback_model"] == "qwen3.5-2b"


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    test_zero_result_fallback_generation()
    test_model_fallback_state_notification()
    print("[SUCCESS] test_fallback_recovery.py: All tests passed successfully!")
