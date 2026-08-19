# tests/test_cross_chatbot_latency.py
"""
통합 3대 챗봇 UI 렌더링 및 콜백 디스패치 오버헤드 벤치마크 테스트 (<50ms 목표)
"""

import time
import sys
import html
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from bteam.Oliview_chatbot_a.common.step_callback import clean_product_name_for_search, build_oliveyoung_search_url


def benchmark_callback_and_sanitization():
    # 1. 600회 상품명 정제 및 URL 빌드
    t_start = time.perf_counter()
    sample_names = [
        "[단독기획] 컬러그램 탕후루 탱글 꿀로스 2종 (+미니글로스 증정)",
        "[1+1기획] 식물나라 산소수 워터프루프 선크림 60ml 더블기획",
        "헤라 블랙쿠션 SPF34 PA++ 본품 15g + 리필 15g [21호]",
    ] * 200

    for name in sample_names:
        clean = clean_product_name_for_search(name, "브랜드")
        url = build_oliveyoung_search_url(name, "브랜드")
        _ = html.escape(clean)

    elapsed_ms = (time.perf_counter() - t_start) * 1000.0
    print(f"[BENCHMARK] 600 iterations latency: {elapsed_ms:.3f}ms")

    # Budget is 50ms for the entire batch
    assert elapsed_ms < 50.0, f"Overhead exceeded 50ms budget: {elapsed_ms:.3f}ms"
    print("[PASS] Benchmark within 50ms budget")


if __name__ == "__main__":
    benchmark_callback_and_sanitization()
    print("[SUCCESS] All test_cross_chatbot_latency.py tests passed!")
