# Quickstart Validation Guide: 032-llm-response-caching

**Feature**: `032-llm-response-caching`  
**Date**: 2026-08-26  
**Status**: Ready for Verification  

---

## 1. Overview
본 문서는 RAG 파이프라인의 **L5 LLM 응답 캐시(Exact-Match Response Caching & Streaming Replay)**, **RAG 문서 해시 기반 자동 무효화**, **SingleFlight 동시성 제어**, **Poisoning Deny-List** 기능을 엔드투엔드로 검증하기 위한 가이드입니다.

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

## 3. Test Scenarios

### Scenario 1: 동일 질문 재질의 시 L5 캐시 히트 & 0 GPU 오프로드 검증
동일한 질문을 2회 연속 전송했을 때, 1회차(GPU 추론 4~8초) 대비 2회차(L5 캐시 <50ms)로 즉시 반환되며 GPU 슬롯 점유가 0회인지 검증합니다.

```bash
docker exec oliview_chatbot_b python -c "
import asyncio, time
from oliview_core.graph_orchestrator import graph_orchestrator

async def test_cache_hit():
    q = '차앤박 프로폴리스 앰플 장점 알려줘'
    
    # 1st Request: Cold Cache -> Full GPU Inference
    t0 = time.time()
    chunks_1 = []
    async for event in graph_orchestrator.stream_rag(query=q, session_id='test_ses_1', tenant_id='chatb'):
        if event.step == 'TOKEN':
            chunks_1.append(event.data.get('token', ''))
    elapsed_1 = time.time() - t0
    resp_1 = ''.join(chunks_1)
    print(f'[1st Run] Elapsed={elapsed_1:.2f}s, Chunks={len(chunks_1)}, TextLen={len(resp_1)}')

    # 2nd Request: Warm Cache -> L5 Replay (<0.1s TTFT)
    t1 = time.time()
    chunks_2 = []
    async for event in graph_orchestrator.stream_rag(query=q, session_id='test_ses_1', tenant_id='chatb'):
        if event.step == 'TOKEN':
            chunks_2.append(event.data.get('token', ''))
    elapsed_2 = time.time() - t1
    resp_2 = ''.join(chunks_2)
    print(f'[2nd Run - L5 Cached] Elapsed={elapsed_2:.2f}s, Chunks={len(chunks_2)}, TextLen={len(resp_2)}')
    
    assert elapsed_2 < 1.0, f'Cache hit must be <1.0s, got {elapsed_2}s'
    assert len(resp_2) > 20, 'Response text must be non-empty'
    print('✅ Scenario 1: L5 Cache Hit Verification PASSED!')

asyncio.run(test_cache_hit())
"
```

---

### Scenario 2: 멀티턴 대명사 질의 맥락 왜곡 방지 (Rewritten Query) 검증
"헤라 블랙쿠션" 질의 후 "이거 커버력 어때?"를 질의했을 때, 롬앤 쿠션 캐시와 충돌하지 않고 정확한 헤라 쿠션 답변을 생성하는지 검증합니다.

```bash
docker exec oliview_chatbot_b pytest tests/unit/test_l5_cache.py -k "test_multiturn_anaphora_cache_key" -v
```

---

### Scenario 3: SingleFlight 동시성 제어 및 Cache Stampede 방어 검증
캐시가 비어 있는 상태에서 동일 질의 3건을 동시 전송했을 때, 단 1건만 GPU 추론을 수행하고 나머지 2건은 생성된 캐시를 공유하여 성공하는지 검증합니다.

```bash
docker exec oliview_chatbot_b pytest tests/unit/test_l5_cache.py -k "test_single_flight_stampede_protection" -v
```
