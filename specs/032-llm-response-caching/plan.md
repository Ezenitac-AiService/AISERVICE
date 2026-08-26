# Implementation Plan: 032-llm-response-caching

**Branch**: `032-llm-response-caching` | **Date**: 2026-08-26 | **Spec**: [`spec.md`](file:///c:/AISERVICE/specs/032-llm-response-caching/spec.md)

**Input**: Feature specification from `/specs/032-llm-response-caching/spec.md`

---

## 1. Summary

단일 GPU(8~11GB VRAM, `active_slots=1`) 환경에서 동일하거나 중복된 RAG 질의에 대해 불필요한 GPU 추론(4~10초)을 제거하고, Redis 기반 **L5 LLM 응답 캐시(Exact-Match Response Caching & Word-Boundary Streaming Replay)**를 구축합니다.
2026년 프로덕션 방어 표준에 맞춰 **탈맥락화 질의 정규화(Rewritten Query Normalization)**, **RAG 검색 문서 해시 기반 자동 무효화(Context Invalidation)**, **SingleFlight 분산 락 & TTL Jitter(12h ± 1h) 기반 Cache Stampede 방지**, **Cache Poisoning Deny-List 가드**, **단어 경계 스트리밍 Replay**를 통합 구현합니다.

---

## 2. Technical Context

* **Language/Version**: Python 3.12, FastAPI 0.115+, Uvicorn 0.32+, Streamlit 1.40+
* **Primary Dependencies**: `redis` (5.0+), `asyncio`, `httpx` (0.28+), `pydantic`, `unicodedata`
* **Storage**: Redis 7.2 (`aiservice-redis:6379`, L1~L5 Cache), MySQL 8.0 (Oliveyoung Products Master)
* **Testing**: `pytest`, `pytest-asyncio`, Unit/Integration Test Suite
* **Target Platform**: Docker Linux Container (`oliview_chatbot_a`, `oliview_chatbot_b`, `aiservice-redis`)
* **Project Type**: Distributed RAG Caching Engine & AI Inference Optimization
* **Performance Goals**:
  * 캐시 히트 시 첫 토큰 지연 시간(TTFT): **< 50ms** (99% 이상 단축)
  * 캐시 히트 시 모델 게이트웨이 GPU 부하: **0 GPU 연산 (100% 오프로드)**
  * 캐시 만료 시 Cache Stampede 방어율: **100% (동시 요청 1개만 GPU 수행)**
* **Constraints**:
  * Redis 소켓 타임아웃 `0.2s` Fail-Fast (장애 시 GPU 자동 Fallback)
  * OpenAI 호환 SSE 스트리밍 규격 100% 보존
* **Scale/Scope**:
  * Chat A (Streamlit) & Chat B (Web UI) 멀티 테넌트 실시간 서빙

---

## 3. Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Compliance Assessment | Status |
|---|---|:---:|
| **I. 언어 및 커뮤니케이션** | 모든 명세, 설계, 주석, 로깅 및 UI 메시지는 한국어 표기 | ✅ PASS |
| **II. TDD 및 계약 검증** | L5 스키마 계약(`contracts/l5_cache_contract.md`) 및 단위/동시성 테스트 선행 구축 | ✅ PASS |
| **III. 서비스 격리 및 무결성** | `oliview_core` 내 모듈화 구현 및 기존 L1~L4 캐시/DB 스키마 비파괴적 보존 | ✅ PASS |
| **IV. 구조화된 로깅** | 캐시 히트/미스, 절감 지연시간(`latency_saved_s`), 키 해시를 구조화 로깅 | ✅ PASS |
| **V. YAGNI & 점진적 진화** | 무거운 벡터 유사도 대신 100% 결정론적인 정규화 Exact Match 및 락 기반 단순 아키텍처 채택 | ✅ PASS |

---

## 4. Project Structure & Changes

### Documentation (this feature)
```text
specs/032-llm-response-caching/
├── plan.md              # This file
├── research.md          # 5 Production Decisions (SingleFlight, Jitter, Replay, Deny-List, Decontextualization)
├── data-model.md        # L5CacheKeyParams, L5ResponseCachePayload, CacheReplayChunk
├── quickstart.md        # Concurrency & Cache Hit Validation Scenarios
├── contracts/           # Redis Key, Payload & SSE Event Contract
│   └── l5_cache_contract.md
└── checklists/
    └── requirements.md  # 16/16 Checked
```

### Source Code Changes

#### 1) Oliview Core (`bteam/oliview_core/`)
* **[MODIFY] [`config.py`](file:///c:/AISERVICE/bteam/oliview_core/config.py)**:
  * `redis_ttl_llm_response: int = 43200` (12시간 기본 TTL) 추가.
  * `redis_ttl_llm_jitter: int = 3600` (±1시간 Jitter 윈도우) 추가.
  * `enable_l5_cache: bool = True` 피처 플래그 추가.
* **[MODIFY] [`redis_pool.py`](file:///c:/AISERVICE/bteam/oliview_core/redis_pool.py)**:
  * `build_l5_key(tenant_id, rewritten_query, doc_ids, model_id, prompt_version)` 구현.
  * `get_l5_response(key)` & `set_l5_response(key, payload, ttl_base, jitter)` 구현 (Deny-List 검증 포함).
  * `replay_cached_stream(cached_payload, chunk_delay_s=0.025)` 비동기 Replay 제너레이터 구현.
* **[MODIFY] [`nodes/synthesis_node.py`](file:///c:/AISERVICE/bteam/oliview_core/nodes/synthesis_node.py)**:
  * LLM 생성 호출 전 L5 캐시 사전 조회 (`get_l5_response`).
  * 캐시 히트 시 `replay_cached_stream`으로 즉시 스트리밍 반환 (GPU 호출 0%).
  * 캐시 미스 시 `SingleFlightLock` 획득 후 LLM 생성 완료 전문을 수집하여 L5 캐시에 저장.
* **[MODIFY] [`graph_orchestrator.py`](file:///c:/AISERVICE/bteam/oliview_core/graph_orchestrator.py)**:
  * `stream_rag`에서 L5 캐시 히트 이벤트(`StepCode.SYNTHESIS`, `is_cached=True`) 처리 및 로깅.

#### 2) Tests (`bteam/tests/`)
* **[NEW] [`tests/unit/test_l5_cache.py`](file:///c:/AISERVICE/bteam/tests/unit/test_l5_cache.py)**:
  * L5 키 생성(NFKC 정규화, 대명사 탈맥락화, 문서 정렬 해시) 단위 테스트.
  * Poisoning Deny-List(에러 문구, 20자 미만) 차단 검증.
  * SingleFlight 동시성 제어 및 TTL Jitter 검증.
* **[NEW] [`tests/integration/test_l5_cache_integration.py`](file:///c:/AISERVICE/bteam/tests/integration/test_l5_cache_integration.py)**:
  * RAG 파이프라인 엔드투엔드 동일 질문 재질의 시 L5 캐시 히트 & TTFT < 50ms 검증.

---

## 5. Verification Plan

1. **단위 테스트**:
   * `pytest tests/unit/test_l5_cache.py -v`
   * 키 생성 무결성, 정규화, Deny-List, TTL Jitter 100% 통과 검증.
2. **통합 및 동시성 테스트**:
   * `docker exec oliview_chatbot_b pytest tests/integration/test_l5_cache_integration.py -v`
   * 동일 질의 2회 연속 호출 시 2회차 TTFT < 50ms 및 GPU 큐 미인입 확인.
   * `SingleFlight` 동시성 3개 요청 인입 시 GPU 1회만 호출됨을 확인.
