# tests/test_chata_stream.py
"""
올리챗 A (Streamlit) 4단계 콜백 및 세션 큐 (pending_query) 계약 테스트
"""

import os
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "bteam" / "Oliview_chatbot_a"))

from bteam.Oliview_chatbot_a.common.step_callback import (
    PipelinePhase,
    StepEvent,
    ReferenceReview,
    RagExecutionMetadata,
    clean_product_name_for_search,
    build_oliveyoung_search_url,
)


class MockStreamlitStatus:
    def __init__(self):
        self.updates = []
        self.label = ""
        self.state = "running"
        self.expanded = True

    def update(self, label: str, state: str = "running", expanded: bool = True):
        self.label = label
        self.state = state
        self.expanded = expanded
        self.updates.append({"label": label, "state": state, "expanded": expanded})


def test_chata_noise_filter_and_url_builder():
    raw_name = "[단독기획] 컬러그램 탕후루 탱글 꿀로스 2종 기획세트 (50ml + 미니글로스 증정)"
    brand = "컬러그램"
    clean_name = clean_product_name_for_search(raw_name, brand)
    assert "단독기획" not in clean_name
    assert "증정" not in clean_name
    assert "50ml" not in clean_name
    assert clean_name.startswith("컬러그램")

    url = build_oliveyoung_search_url(raw_name, brand)
    assert url.startswith("https://www.oliveyoung.co.kr/store/search/getSearchMain.do?query=")
    assert "getSearchMain.do" in url
    print("[PASS] test_chata_noise_filter_and_url_builder")


def test_chata_pending_query_queue_pattern():
    # Simulate single entry queue behavior
    session_state = {"messages": [], "pending_query": None}

    # User clicks chip
    chip_query = "차앤박 앰플 수분감"
    session_state["pending_query"] = chip_query

    # Main evaluation loop consumes and clears queue
    active_query = None
    if session_state.get("pending_query"):
        active_query = session_state["pending_query"]
        session_state["pending_query"] = None  # Consume and clear

    assert active_query == "차앤박 앰플 수분감"
    assert session_state["pending_query"] is None  # Queue cleared to prevent double trigger
    print("[PASS] test_chata_pending_query_queue_pattern")


def test_chata_callback_lifecycle():
    status = MockStreamlitStatus()
    events = [
        StepEvent(phase=PipelinePhase.INTENT_ANALYSIS, label="🔍 의도 분석 중..."),
        StepEvent(phase=PipelinePhase.HYBRID_SEARCH, label="📚 리뷰 검색 중..."),
        StepEvent(phase=PipelinePhase.RERANKING, label="⚖️ 순위 재정렬 중..."),
        StepEvent(phase=PipelinePhase.LLM_SYNTHESIS, label="🧠 맞춤 답변 생성 중..."),
    ]

    for ev in events:
        status.update(label=ev.label, state=ev.status)

    assert len(status.updates) == 4
    assert status.updates[-1]["label"] == "🧠 맞춤 답변 생성 중..."

    # Complete
    metadata = RagExecutionMetadata(
        total_latency_sec=1.8,
        searched_review_count=20,
        selected_review_count=3,
        model_used="qwen3.5-4b",
    )
    status.update(
        label=f"✅ 리뷰 종합 분석 완료 ({metadata.total_latency_sec:.1f}초, {metadata.selected_review_count}건 참조)",
        state="complete",
        expanded=False,
    )
    assert status.state == "complete"
    assert status.expanded is False
    print("[PASS] test_chata_callback_lifecycle")


if __name__ == "__main__":
    test_chata_noise_filter_and_url_builder()
    test_chata_pending_query_queue_pattern()
    test_chata_callback_lifecycle()
    print("[SUCCESS] All test_chata_stream.py tests passed!")
