# tests/test_sse_stream_b.py
"""
올리챗 B SSE 스트림 엔드포인트 이벤트 포맷 및 계약 테스트
"""

import sys
import os
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "bteam" / "Oliview_chatbot_b"))

from common import (
    PipelinePhase,
    StepEvent,
    ReferenceReview,
    RagExecutionMetadata,
    FallbackRecommendation,
)


def format_sse_message(event: str, data: dict | str) -> str:
    """SSE 프로토콜 형식 메시지 직렬화 헬퍼"""
    payload = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else str(data)
    return f"event: {event}\ndata: {payload}\n\n"


def parse_sse_stream(raw_stream: str) -> list[tuple[str, dict | str]]:
    """수신된 SSE 스트림 텍스트 파싱 헬퍼"""
    events = []
    blocks = raw_stream.strip().split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        lines = block.split("\n")
        evt_type = "message"
        data_str = ""
        for line in lines:
            if line.startswith("event:"):
                evt_type = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_str = line[len("data:"):].strip()
        try:
            parsed_data = json.loads(data_str)
        except Exception:
            parsed_data = data_str
        events.append((evt_type, parsed_data))
    return events


def test_sse_event_formatting():
    """SSE 이벤트 직렬화 및 역직렬화 무결성 검증"""
    step_data = {
        "phase": PipelinePhase.INTENT_ANALYSIS.value,
        "label": "🔍 의도 분석 중",
        "status": "running",
        "elapsed_sec": 0.05,
        "progress_percent": 25,
    }
    raw_sse = format_sse_message("step", step_data)
    assert raw_sse.startswith("event: step\n")
    assert "data: {" in raw_sse

    parsed = parse_sse_stream(raw_sse)
    assert len(parsed) == 1
    assert parsed[0][0] == "step"
    assert parsed[0][1]["phase"] == "INTENT_ANALYSIS"
    assert parsed[0][1]["progress_percent"] == 25


def test_sse_complete_and_reference_reviews_flow():
    """SSE 스트림의 step -> token -> complete 전체 수명 주기 프레이밍 검증"""
    stream_output = []

    # 1. Step Events
    for phase, label, pct in [
        (PipelinePhase.INTENT_ANALYSIS, "🔍 의도 분석 중", 25),
        (PipelinePhase.HYBRID_SEARCH, "📚 하이브리드 검색 중", 50),
        (PipelinePhase.RERANKING, "⚖️ 리랭킹 중", 75),
        (PipelinePhase.LLM_SYNTHESIS, "🧠 LLM 생성 중", 90),
    ]:
        stream_output.append(
            format_sse_message(
                "step",
                {"phase": phase.value, "label": label, "status": "running", "progress_percent": pct},
            )
        )

    # 2. Token Events
    tokens = ["식물", "나라 ", "선크림", "은 지속력이 뛰어납니다."]
    for tok in tokens:
        stream_output.append(format_sse_message("token", {"token": tok}))

    # 3. Complete Event
    complete_payload = {
        "phase": PipelinePhase.COMPLETED.value,
        "label": "✅ 리뷰 종합 분석 완료",
        "total_latency_sec": 1.25,
        "searched_review_count": 20,
        "selected_review_count": 3,
        "model_used": "qwen3.5-4b",
        "fallback_triggered": False,
        "reference_reviews": [
            {
                "rank": 1,
                "product_name": "선크림",
                "brand_name": "식물나라",
                "category": "선케어",
                "review_score": 5,
                "attribute_tag": "지속력",
                "sentiment_label": "긍정",
                "separated_sentence": "하루 종일 지속되네요.",
                "rerank_score": 0.92,
            }
        ],
    }
    stream_output.append(format_sse_message("complete", complete_payload))

    full_stream = "".join(stream_output)
    parsed_events = parse_sse_stream(full_stream)

    assert len(parsed_events) == 4 + len(tokens) + 1
    assert parsed_events[0][0] == "step"
    assert parsed_events[4][0] == "token"
    assert parsed_events[-1][0] == "complete"
    assert parsed_events[-1][1]["selected_review_count"] == 3
    assert len(parsed_events[-1][1]["reference_reviews"]) == 1


def test_sse_error_and_recovery_payload():
    """SSE 오류 발생 시 에러 이벤트 및 복구 칩 페이로드 검증"""
    error_payload = {
        "phase": PipelinePhase.ERROR.value,
        "label": "⚠️ 분석 실패",
        "error_message": "등록된 리뷰가 없습니다.",
        "retry_query": "식물나라 선크림",
        "suggested_chips": ["식물나라", "선케어", "선크림 지속력"],
    }
    sse_msg = format_sse_message("error", error_payload)
    parsed = parse_sse_stream(sse_msg)

    assert len(parsed) == 1
    assert parsed[0][0] == "error"
    assert parsed[0][1]["retry_query"] == "식물나라 선크림"
    assert len(parsed[0][1]["suggested_chips"]) == 3


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    test_sse_event_formatting()
    test_sse_complete_and_reference_reviews_flow()
    test_sse_error_and_recovery_payload()
    print("[SUCCESS] test_sse_stream_b.py: All 3 SSE contract tests passed successfully!")
