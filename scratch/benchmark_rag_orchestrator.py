"""
A/B RAG Performance Parity & Latency Benchmark (Spec 030 T038).
10개 대표 질의(단일/비교/장단점/기능)에 대한 전처리 및 E2E 지연시간 벤치마크.
"""

import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bteam")))

from oliview_core.graph_orchestrator import MultiTargetGraphOrchestrator
from oliview_core.logger import get_logger

logger = get_logger("oliview.benchmark")

BENCHMARK_QUERIES = [
    # 1. 단일 제품 질의 (3종)
    "차앤박 프로폴리스 앰플 수분감 어때?",
    "헤라 블랙쿠션 지속력 괜찮아?",
    "식물나라 티트리 토너 진정 효과 있어?",
    # 2. 명시적 2개 제품 비교 질의 (3종)
    "차앤박 프로폴리스 앰플이랑 식물나라 시카 토너 수분감 비교해줘",
    "헤라 블랙쿠션이랑 클리오 쿠션 커버력 비교해줘",
    "CNP 앰플과 Dr.G 크림 보습력 비교해줘",
    # 3. 기능/속성 기반 다자 비교 질의 (2종)
    "속건조에 좋은 인기 앰플들 비교해줘",
    "진정 효과 좋은 스킨케어 제품들 추천해줘",
    # 4. 장단점 객관 분석 질의 (2종)
    "헤라 블랙쿠션 장단점 솔직하게 알려줘",
    "차앤박 프로폴리스 앰플 솔직 후기 분석해줘",
]


def run_benchmark():
    print("=" * 70)
    print("🚀 Oliview RAG Orchestrator Latency & Parity Benchmark (Spec 030)")
    print("=" * 70)

    orchestrator = MultiTargetGraphOrchestrator()
    results = []

    for idx, query in enumerate(BENCHMARK_QUERIES, start=1):
        print(f"\n[{idx}/10] 쿼리 실행: '{query}'")
        t_start = time.perf_counter()

        step_events = []
        token_count = 0
        is_fallback = False
        metrics = {}

        try:
            for event in orchestrator.stream_rag(query, session_id=f"bench_sess_{idx}"):
                evt_type = event.get("event_type", "")
                if evt_type == "step_update":
                    step_events.append(event)
                elif evt_type == "token":
                    token_count += 1
                elif evt_type == "fallback_alert":
                    is_fallback = True
                elif evt_type == "complete":
                    metrics = event.get("metrics", {})

            total_sec = time.perf_counter() - t_start
            pattern = step_events[0].get("step_name", "UNKNOWN") if step_events else "N/A"

            res = {
                "idx": idx,
                "query": query[:35] + ("..." if len(query) > 35 else ""),
                "latency_sec": round(total_sec, 2),
                "tokens": token_count,
                "fallback": "Y" if is_fallback else "N",
            }
            results.append(res)
            print(f"  └─ 소요 시간: {total_sec:.2f}초 | 토큰: {token_count}개 | 폴백: {res['fallback']}")

        except Exception as e:
            print(f"  └─ ❌ 오류 발생: {e}")
            results.append({
                "idx": idx,
                "query": query[:35],
                "latency_sec": -1,
                "tokens": 0,
                "fallback": "ERROR",
            })

    print("\n" + "=" * 70)
    print("📊 벤치마크 결과 요약")
    print("=" * 70)
    print(f"{'No':<4} | {'질문':<38} | {'소요시간':<8} | {'토큰수':<6} | {'폴백'}")
    print("-" * 70)
    for r in results:
        print(f"{r['idx']:<4} | {r['query']:<38} | {r['latency_sec']:<6}초 | {r['tokens']:<6} | {r['fallback']}")
    print("=" * 70)


if __name__ == "__main__":
    run_benchmark()
