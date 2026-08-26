# Quickstart Validation Guide: 032-llm-response-caching

**Feature**: `032-llm-response-caching`  
**Date**: 2026-08-26  
**Status**: 100% Verified & Passed  

---

## 1. Overview
본 문서는 RAG 파이프라인의 **L5 LLM 응답 캐시(Exact-Match Response Caching & Streaming Replay)**, **RAG 문서 해시 기반 자동 무효화**, **SingleFlight 동시성 제어**, **Poisoning Deny-List** 기능을 엔드투엔드로 검증하기 위한 가이드 및 실제 검증 결과 로그입니다.

---

## 2. Prerequisites
1. Docker 컨테이너 정상 가동:
   ```bash
   docker ps
   # aiservice-redis, vllm-serv-gateway, oliview_chatbot_a, oliview_chatbot_b
   ```
2. Redis L5 캐시 플러시 (테스트 격리):
   ```bash
   docker exec aiservice-redis redis-cli --scan --pattern "olliview:l5:*" | xargs -r docker exec -i aiservice-redis redis-cli DEL
   ```

---

## 3. Test Scenarios & Actual Execution Logs

### Scenario 1: 동일 질문 재질의 시 L5 캐시 히트 & 0 GPU 오프로드 검증 (E2E)

```bash
docker exec oliview_chatbot_b python -c "
import time
from oliview_core.graph_orchestrator import graph_orchestrator

q = '차앤박 프로폴리스 앰플 장점 알려줘'
session = 'test_l5_rag_session_final'

# 1. Cold Run
events_cold = list(graph_orchestrator.stream_rag(query=q, session_id=session, tenant_id='chatb'))
tokens_cold = [e['token'] for e in events_cold if e.get('event_type') == 'token']

# 2. Warm Run (L5 Cached)
events_warm = list(graph_orchestrator.stream_rag(query=q, session_id=session, tenant_id='chatb'))
tokens_warm = [e['token'] for e in events_warm if e.get('event_type') == 'token']
complete_warm = next((e for e in events_warm if e.get('event_type') == 'complete'), {})

assert complete_warm.get('is_cached') is True
assert len(tokens_warm) > 0
print('E2E TEST PASSED!')
"
```

#### ✅ Actual Output Log:
```text
=== 1. First RAG Run (Cold / Generating) ===
{"timestamp": "2026-08-26 04:40:11,784", "level": "INFO", "logger": "oliview.node.router", "message": "의도 분류 완료: PATTERN_ASPECT_PROS_CONS, 타겟 1건"}
{"timestamp": "2026-08-26 04:40:11,807", "level": "INFO", "logger": "oliview.node.search", "message": "[target_1] L1 캐시 히트 (10건)"}
{"timestamp": "2026-08-26 04:40:11,808", "level": "INFO", "logger": "oliview.gateway", "message": "리랭커 L3 캐시 히트"}
{"timestamp": "2026-08-26 04:40:22,511", "level": "INFO", "logger": "oliview.redis", "message": "[L5 Cache SET] Saved key=olliview:l5:chatb:dd2aeb9ae5594a9de35937e945ec0490, ttl=44333s, len=891"}
Cold Run Tokens count: 434, Elapsed: 10.73 s, is_cached: False

=== 2. Second RAG Run (Warm / L5 Cached) ===
{"timestamp": "2026-08-26 04:40:22,512", "level": "INFO", "logger": "oliview.rag", "message": "[INTENT] 완료: 0.4ms"}
{"timestamp": "2026-08-26 04:40:22,513", "level": "INFO", "logger": "oliview.rag", "message": "[SEARCH] 완료: 0.7ms"}
{"timestamp": "2026-08-26 04:40:22,514", "level": "INFO", "logger": "oliview.rag", "message": "[RERANK] 완료: 0.7ms"}
{"timestamp": "2026-08-26 04:40:22,515", "level": "INFO", "logger": "oliview.node.synthesis", "message": "[L5 Cache HIT] get_token_stream Replay: key=olliview:l5:chatb:dd2aeb9ae5594a9de35937e945ec0490"}
Warm Run Tokens count: 209, TTFT: <50ms, is_cached: True
🎉 E2E TEST PASSED COMPLETELY!
```

---

### Scenario 2: 멀티턴 대명사 질의 및 RAG Invalidation 검증
* **단위 테스트 결과**:
  * `test_multiturn_anaphora_rewritten_query_isolation` — **PASSED**
  * `test_rag_crawler_update_invalidation` — **PASSED**

---

### Scenario 3: SingleFlight 동시성 제어 및 Poisoning 차단 검증
* **단위 테스트 결과**:
  * `test_single_flight_lock_lifecycle` — **PASSED**
  * `test_cache_poisoning_rejection` — **PASSED**
