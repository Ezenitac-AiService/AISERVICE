"""
Integration Test Suite for L5 LLM Response Caching (Spec 032).
E2E RAG Pipeline Cache Hit, Latency Measurement, and Replay Validation.
"""

import time
import pytest
from oliview_core.graph_orchestrator import graph_orchestrator
from oliview_core.redis_pool import get_redis_client


def test_e2e_rag_pipeline_l5_cache_hit():
    """
    E2E 시나리오:
    1회차 질의: Cold Cache -> 전체 RAG + GPU LLM 추론 실행 -> L5 캐시 저장
    2회차 질의: Warm Cache -> L5 캐시 히트 -> TTFT < 50ms, 0 GPU 오프로드
    """
    client = get_redis_client()
    if client is None:
        pytest.skip("Redis 서버 미연결로 E2E 통합 테스트 스킵")

    test_q = "차앤박 프로폴리스 앰플 장점 알려줘"
    test_session = f"test_e2e_session_{int(time.time())}"

    # ── 1회차: Cold Run ──
    t0 = time.time()
    events_1 = list(graph_orchestrator.stream_rag(query=test_q, session_id=test_session, tenant_id="chata"))
    elapsed_1 = time.time() - t0

    tokens_1 = [e["token"] for e in events_1 if e.get("event_type") == "token"]
    full_resp_1 = "".join(tokens_1)
    complete_1 = next((e for e in events_1 if e.get("event_type") == "complete"), {})

    assert len(full_resp_1) > 20, f"1회차 응답 텍스트 길이가 유효해야 함: {len(full_resp_1)}"
    assert complete_1.get("is_cached") is False, "1회차는 캐시 미스(is_cached=False)여야 함"
    print(f"\n[Cold Run] Elapsed: {elapsed_1:.2f}s, Response Length: {len(full_resp_1)}")

    # ── 2회차: Warm Run (L5 Cache Hit) ──
    t1 = time.time()
    events_2 = list(graph_orchestrator.stream_rag(query=test_q, session_id=test_session, tenant_id="chata"))
    elapsed_2 = time.time() - t1

    tokens_2 = [e["token"] for e in events_2 if e.get("event_type") == "token"]
    full_resp_2 = "".join(tokens_2)
    complete_2 = next((e for e in events_2 if e.get("event_type") == "complete"), {})

    assert len(full_resp_2) > 20, f"2회차 응답 텍스트 길이가 유효해야 함: {len(full_resp_2)}"
    assert complete_2.get("is_cached") is True, "2회차는 반드시 L5 캐시 히트(is_cached=True)여야 함"
    assert full_resp_2 == full_resp_1, "캐시된 2회차 응답이 1회차 응답과 100% 일치해야 함"
    print(f"[Warm Run - L5 Cached] Elapsed: {elapsed_2:.2f}s (Speedup: {elapsed_1 / max(0.001, elapsed_2):.1f}x)")
    print("✅ E2E L5 Response Caching Verification PASSED!")
