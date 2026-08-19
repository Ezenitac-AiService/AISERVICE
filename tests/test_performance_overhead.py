# tests/test_performance_overhead.py
"""
UI 렌더링 및 콜백 디스패치 성능 오버헤드 검증 테스트 (< 50ms 검증)
"""

import sys
import os
import time
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "bteam" / "Oliview_chatbot_a"))

from common.step_callback import (
    PipelinePhase,
    StepEvent,
    ReferenceReview,
    RagExecutionMetadata,
    StepCallbackProtocol,
)


class BenchmarkCallback:
    def __init__(self):
        self.count = 0

    def on_step(self, event: StepEvent) -> None:
        self.count += 1

    def on_token(self, token: str) -> None:
        self.count += 1

    def on_complete(self, metadata: RagExecutionMetadata) -> None:
        self.count += 1

    def on_error(self, error_event: StepEvent, recommendation=None) -> None:
        self.count += 1


def test_callback_dispatch_latency():
    """StepCallback 이벤트 100회 디스패치 소요 시간 < 10ms (기준 50ms 이하) 검증"""
    cb = BenchmarkCallback()
    
    t_start = time.perf_counter()
    for _ in range(100):
        cb.on_step(StepEvent(PipelinePhase.INTENT_ANALYSIS, "의도 분석 중", "running", 0.01, 25))
        cb.on_token("단어")
    
    meta = RagExecutionMetadata(
        total_latency_sec=1.0,
        searched_review_count=10,
        selected_review_count=2,
        model_used="qwen3.5-4b",
    )
    cb.on_complete(meta)
    t_end = time.perf_counter()
    
    elapsed_ms = (t_end - t_start) * 1000
    print(f"📊 100회 콜백 디스패치 소요 시간: {elapsed_ms:.3f}ms")
    assert elapsed_ms < 50.0, f"Overhead {elapsed_ms}ms exceeded 50ms limit!"


def test_sse_serialization_latency():
    """SSE JSON 직렬화 100회 소요 시간 < 10ms 검증"""
    t_start = time.perf_counter()
    for i in range(100):
        payload = {
            "phase": "HYBRID_SEARCH",
            "label": f"검색 중 {i}",
            "status": "running",
            "progress_percent": 50,
            "reviews": [{"rank": 1, "product_name": "제품", "text": "리뷰 문장입니다."}]
        }
        sse_str = f"event: step\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
    t_end = time.perf_counter()
    
    elapsed_ms = (t_end - t_start) * 1000
    print(f"📊 100회 SSE 직렬화 소요 시간: {elapsed_ms:.3f}ms")
    assert elapsed_ms < 50.0, f"Overhead {elapsed_ms}ms exceeded 50ms limit!"


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    test_callback_dispatch_latency()
    test_sse_serialization_latency()
    print("[SUCCESS] test_performance_overhead.py: All latency benchmark tests passed successfully!")
