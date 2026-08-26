# Feature Specification: 032-llm-response-caching

**Feature Branch**: `032-llm-response-caching`  
**Created**: 2026-08-26  
**Status**: Draft  
**Input**: User description: "챗봇이 완전히 같은 질문을 받았을때에, 임베딩, 리랭킹 등은 redis를 이용한 캐시 사용을 해서, 빠르게 처리를 하는데, 최종 llm 답변은 다시 생성하네, 이게 맞나? 타당성 검토하고, 2026년 8월 최신 업계 트랜드를 리서치해서 분석해봐"

---

## 1. Background & 2026 Industry Trend Analysis (2026년 8월 기준)

### 1.1 배경 및 문제 정의 (Problem Statement & Feasibility)
* **현재 시스템 아키텍처 한계**:
  * 현재 `oliview_core` RAG 파이프라인은 1차 검색 풀(L1), BGE-M3 임베딩 벡터(L2), 리랭커 점수(L3), 세션 체크포인트(L4)를 Redis에 캐싱하여 검색/선별 단계를 50ms 이내로 단축했습니다.
  * 그러나 **완전히 동일한 질문(예: "차앤박 프로폴리스 앰플 장점 알려줘")이 다시 인입되었을 때**, 검색/임베딩/리랭킹은 캐시를 통해 즉시 통과하지만, 마지막 **Synthesis Node(LLM 텍스트 생성 단계)는 캐시 레이어가 없어 매번 LLM GPU 추론(4~10초)을 재실행**합니다.
* **단일 GPU 환경에서의 치명적 비효율**:
  * 단일 GPU(8~11GB VRAM, `active_slots=1`) 환경에서 동일 질의에 대해 불필요한 GPU 디코딩 연산을 반복 수행함으로써, 전력 및 VRAM 대역폭이 낭비되고 다른 대기 사용자의 요청이 큐에 불필요하게 적재(Head-of-Line Blocking)되는 병목이 발생합니다.
* **타당성 검토 결과**:
  * **사용자의 지적이 100% 타당함**. RAG 시스템에서 동일한 사용자 질의 및 동일한 근거 문서 기반의 생성 결과는 결정론적(Deterministic) 가치가 높으므로, **L5 레벨의 LLM 최종 응답 캐시(Exact-Match & Semantic Response Cache)** 구축이 필수적입니다.

---

### 1.2 2026년 8월 최신 업계 트렌드 및 방법론 분석

2026년 프로덕션 LLM 및 RAG 서빙 생태계(vLLM, SGLang Router, LiteLLM, Redis AI Gateway)의 3계층 응답 최적화 표준은 다음과 같습니다:

```
[2026 LLM Caching Hierarchy]
┌─────────────────────────────────────────────────────────────┐
│ Level 1: Exact-Match Key-Value Cache (Redis)                │  <-- 본 명세 타겟 (L5)
│  - Hashing: (User Query + Retrieved Doc IDs + Prompt Ver)   │  - 지연시간: < 10ms
│  - 비용/GPU 부하: 0 GPU Compute, 100% Deterministic         │  - 적중률: 20~40%
├─────────────────────────────────────────────────────────────┤
│ Level 2: Semantic Intent Cache (Vector Similarity 0.90+)    │
│  - 의미적 유사 질의 매칭 (임계치 가드레일 필요)            │
├─────────────────────────────────────────────────────────────┤
│ Level 3: Prompt/KV Prefix Cache (Inference-Level Engine)    │
│  - vLLM/SGLang 시스템 프롬프트 Attention KV 캐시 재사용     │
└─────────────────────────────────────────────────────────────┘
```

1. **Exact-Match First 원칙 (결정론적 0-GPU 서빙)**:
   * 2026년 업계 표준은 불필요한 벡터 연산이나 환각 위험을 배제하기 위해, 1단계로 완전 일치(Exact-Match) 해시 캐시를 최우선 조회합니다.
   * 동일 질의 및 동일 검색 결과셋에 대해 **TTFT(첫 토큰 지연시간)를 4~10초에서 < 10ms(99.9% 단축)**로 개선하며, GPU 연산 부하를 0으로 만듭니다.
2. **Context-Aware Cache Invalidation (RAG 데이터 무결성 보장)**:
   * 단순 질문 텍스트만 캐시 키로 사용할 경우, 상품 정보나 고객 리뷰 데이터가 DB에서 업데이트되었음에도 과거 답변이 반환되는 stale data 문제가 발생합니다.
   * 2026 표준 기법: 캐시 키에 `(정제된 질문 텍스트 + 리랭킹 상위 N개 문서 ID들의 정렬 해시 + 프롬프트 템플릿 버전 + 모델 ID)`를 조합합니다. 이를 통해 **상품/리뷰 데이터가 갱신되어 검색 문서가 바뀌면 자동으로 캐시 미스가 발생하여 최신 정보를 반영**합니다.
3. **High-Speed Streaming Cache Replay (UX 호환성 유지)**:
   * 캐시 히트 시 수천 자의 답변 텍스트를 한 번에 덤프하면 클라이언트(Chat A, Chat B)의 SSE 스트리밍 UI, 마크다운 렌더러, 타이핑 인터랙션이 깨지거나 부자연스러워집니다.
   * 캐시된 텍스트를 클라이언트에 표준 SSE 토큰 청크 형태로 초고속 Replay(예: 100~200 tokens/sec 또는 10ms 간격 분할 스트리밍)하여 프론트엔드 코드 수정 없이 매끄러운 타이핑 효과를 제공합니다.
4. **Single-Flight Lock (Thundering Herd 방지)**:
   * 동일한 인기 질문이 동시에 10건 유입될 때 10개 요청이 모두 GPU로 가지 않고, 1개 요청만 GPU 추론을 실행하고 나머지 9개는 생성 완료된 Redis 캐시를 구독/공유(Spec 031 Request Coalescing과 상호 보완)합니다.

---

## Clarifications

### Session 2026-08-26
- **Q**: 리뷰 수집 및 감정 분석 갱신 주기를 반영한 L5 LLM 응답 캐시의 생명주기(TTL) 및 무효화(Invalidation) 정책을 어떻게 구성할까요?  
  **A**: **Option A 채택 (배치 주기 연동 TTL 12~24시간 + RAG 검색 문서 해시 기반 자동 무효화)** — 크롤러/분석 배치가 실행되어 상위 검색 리뷰나 평점이 바뀌면 검색 노드가 반환하는 `doc_ids_hash`가 변경되어 즉시 자동 캐시 미스 발생. 배치 작업 주기가 도래하지 않아 데이터 변경이 없을 때는 12~24시간(`redis_ttl_llm_response = 43200`초 기본값) 동안 안정적으로 캐시 히트(0 GPU)를 재사용한다.
- **Q**: L5 캐시 히트 시 클라이언트에 전달하는 스트리밍 반환 방식(Streaming Cache Replay)을 어떻게 구현할까요?  
  **A**: **Option A 채택 (고속 스트리밍 Replay)** — 청크당 10~20ms 간격으로 고속 분할 스트리밍하여 프론트엔드 UI(Chat A, Chat B)의 SSE 파서, 마크다운 렌더러 및 타이핑 애니메이션과 100% 호환되며 체감 지연 없이 매끄러운 UX를 보장한다.

---

## 2. User Scenarios & Testing *(mandatory)*

### User Story 1 - 동일 질문에 대한 초고속 LLM 캐시 응답 (Priority: P1) 🎯 MVP

사용자가 이전에 처리된 적이 있는 완전히 동일한 제품/비교 질문을 다시 입력했을 때, 시스템은 GPU 추론을 다시 실행하지 않고 Redis L5 캐시에서 즉시 응답을 인출하여 0.1초 이내에 답변을 스트리밍하기 시작합니다.

* **Why this priority**: 동일 질문 반복 인입 시 GPU 병목을 완전히 제거하고 사용자 응답 속도를 극대화하는 핵심 가치입니다.
* **Independent Test**: Chat A 또는 Chat B에서 "차앤박 프로폴리스 앰플 장점 알려줘"를 1회 질의하여 캐시를 생성한 후, 동일 질문을 재질의했을 때 게이트웨이 GPU 슬롯을 점유하지 않고 50ms 이내에 응답 스트리밍이 개시되는지 검증.
* **Acceptance Scenarios**:
  1. **Given** 과거에 처리되어 Redis L5 캐시에 저장된 질문과 검색 컨텍스트가 존재할 때, **When** 사용자가 동일한 질문을 전송하면, **Then** 모델 게이트웨이에 GPU 추론 요청을 보내지 않고 Redis 캐시에서 즉시 스트림을 생성하여 반환해야 한다.
  2. **Given** 캐시 히트된 응답이 전송될 때, **When** 클라이언트가 SSE 스트림을 수신하면, **Then** 기존 실시간 생성과 동일한 SSE 청크 포맷으로 스트리밍되어 UI 타이핑 애니메이션이 자연스럽게 작동해야 한다.
  3. **Given** 캐시가 적용된 상태에서, **When** 백엔드 처리 지연 시간을 측정하면, **Then** 첫 토큰 응답 시간(TTFT)이 100ms 미만이어야 한다.

---

### User Story 2 - RAG 컨텍스트 변경 시 자동 캐시 무효화 (Priority: P2)

관리자가 올리브영 상품 정보나 리뷰 데이터를 갱신하여 검색된 문서 결과(Doc IDs)가 달라졌을 때, 질문이 동일하더라도 이전의 오래된(Stale) 캐시 답변 대신 새로운 문서를 기반으로 최신 LLM 답변을 재생성합니다.

* **Why this priority**: 이커머스 추천 챗봇에서 가격, 품절 여부, 신규 리뷰 등의 최신 데이터 무결성을 보장하기 위함입니다.
* **Independent Test**: 질문 텍스트는 동일하지만 검색 문서 ID가 달라진 경우, L5 캐시 미스가 발생하여 Synthesis Node가 정상적으로 LLM GPU 추론을 호출하는지 검증.
* **Acceptance Scenarios**:
  1. **Given** 특정 질문에 대한 캐시가 존재하는 상태에서, **When** 검색 노드가 반환한 상위 문서(Top-K Documents)의 ID 조합이 변경되면, **Then** 캐시 키가 달라져 캐시 미스로 판정되고 신규 LLM 생성이 트리거되어야 한다.
  2. **Given** 신규 LLM 생성이 완료되면, **When** 새로운 응답이 생성되면, **Then** 갱신된 문서 ID 해시를 기반으로 새로운 L5 캐시 엔트리가 Redis에 저장되어야 한다.

---

### User Story 3 - 캐시 TTL 만료 및 바이패스 제어 (Priority: P3)

시스템은 캐시의 유효 기간(TTL, 기본 12~24시간)을 관리하여 주기적인 신선도를 유지하고, 디버깅이나 강제 갱신이 필요할 경우 캐시를 우회(Bypass)할 수 있는 옵션을 제공합니다.

* **Why this priority**: 장기 누적 메모리 관리 및 개발/테스트 시 유연성을 제공합니다.
* **Independent Test**: 설정된 TTL(예: 12시간) 경과 후 캐시가 자동 만료되는지 확인하고, `no-cache` 옵션 전달 시 강제 재생성되는지 검증.
* **Acceptance Scenarios**:
  1. **Given** L5 캐시 엔트리가 생성될 때, **When** TTL(12시간)이 설정되면, **Then** 만료 시간이 지난 후 자동 소멸되어야 한다.
  2. **Given** 요청 헤더에 `Cache-Control: no-cache` 또는 `X-Bypass-Cache: true`가 포함되면, **When** 동일 질문이 유입되더라도, **Then** 캐시를 건너뛰고 GPU 추론을 직접 수행해야 한다.

---

### Edge Cases
* **스트리밍 도중 클라이언트 연결 끊김**: LLM이 답변을 생성하는 도중 클라이언트가 탭을 닫아도, 백그라운드에서 생성이 온전히 완료된 경우에만 Redis에 L5 캐시로 커밋하여 불완전한(Truncated) 답변이 캐싱되지 않도록 방지.
* **빈 답변 또는 에러 응답**: LLM 엔진이 에러 메시지나 빈 문자열을 반환한 경우 절대로 Redis에 캐싱하지 않음.
* **Redis 연결 일시 장애(Fail-Fast)**: Redis 서버가 다운되거나 타임아웃(0.2초) 발생 시, 에러를 내지 않고 캐시 미스로 안전하게 Fallback하여 GPU 추론을 직접 수행.
* **단일 GPU 동시 동일 질의(Thundering Herd)**: 동일한 질의가 0.1초 간격으로 동시 유입될 때, SingleFlight 락을 통해 1개만 GPU 추론하고 나머지는 해당 결과의 캐시를 대기/공유.

---

## 3. Requirements *(mandatory)*

### Functional Requirements

* **FR-001 (L5 Exact LLM Response Cache Key)**: `bteam/oliview_core`는 질문 정제 텍스트(`cleaned_query`), 리랭킹된 상위 문서 ID 목록의 정렬 해시(`doc_ids_hash`), 모델 식별자(`model_id`), 프롬프트 템플릿 버전(`prompt_version`)의 조합을 SHA-256 해싱하여 `olliview:l5:exact:<hash>` 포맷의 고유 캐시 키를 생성해야 한다.
* **FR-002 (Synthesis Node L5 Cache Lookup)**: `synthesis_node.py` 및 `graph_orchestrator.py`는 LLM 생성 호출(`client.generate_stream`) 전에 L5 캐시를 우선 조회하여, 캐시 히트 시 GPU 게이트웨이 호출 없이 캐시된 응답을 즉시 반환해야 한다.
* **FR-003 (Streaming Cache Replay Engine)**: 캐시 히트 시, 캐시된 전체 텍스트를 클라이언트의 SSE 파서 및 UI 타이핑 인터랙션 규격에 맞춰 고속 스트리밍 청크(예: 청크당 20~50ms 간격 또는 실시간 토큰 분할)로 재생(Replay)하여 전송해야 한다.
* **FR-004 (Atomicity & Completeness Guard)**: LLM 스트리밍 응답이 정상 종료(`[DONE]` 또는 에러 없음)되고 완성된 전체 텍스트의 길이가 최소 기준(예: > 10자)을 만족할 때만 Redis L5 캐시에 저장해야 한다.
* **FR-005 (Redis L5 TTL Policy)**: L5 LLM 응답 캐시의 TTL 기본값은 12시간(`redis_ttl_llm_response = 43200`초)으로 설정하고, `bteam/oliview_core/config.py`를 통해 동적으로 조정 가능해야 한다.
* **FR-006 (Context Invalidation)**: RAG 검색 풀 또는 리랭커 결과의 문서 조합이 단 하나라도 달라지면 캐시 키 해시가 변경되어 자동으로 최신 LLM 추론을 수행해야 한다.
* **FR-007 (Fail-Fast Redis Fallback)**: Redis 소켓 타임아웃(0.2초) 초과 또는 연결 오류 발생 시 파이프라인 중단 없이 즉시 캐시 미스로 우회하여 GPU 추론을 정상 진행해야 한다.
* **FR-008 (Cache Bypass Support)**: 클라이언트 요청 헤더에 `Cache-Control: no-cache` 또는 `X-Bypass-Cache: true`가 명시된 경우 L5 캐시 조회를 건너뛰고 GPU 추론을 직접 트리거해야 한다.
* **FR-009 (Cache Metrics & Observability)**: L5 캐시 히트/미스 여부, 절감된 GPU 추론 시간(Saved Latency), 캐시 키를 구조화된 로그(`is_cache_hit=True`, `latency_saved_s=X.X`)로 기록하여 관측 가능성을 보장해야 한다.

---

### Key Entities

* **`L5ResponseCachePayload`**: Redis에 직렬화되어 저장되는 완성된 LLM 응답 데이터 구조체.
  * 속성: `response_text` (완성된 답변 텍스트), `model_id`, `created_at` (타임스탬프), `doc_ids` (참조된 문서 ID 목록), `prompt_version`.
* **`CacheReplayStream`**: 캐시된 응답을 실시간 SSE 스트림 형식으로 변환하는 비동기 제너레이터.
  * 속성: `chunk_size`, `interval_ms`, `is_cached` (메타데이터 플래그).

---

## 4. Success Criteria *(mandatory)*

### Measurable Outcomes

* **SC-001 (동일 질의 첫 토큰 응답 속도 단축)**: 동일 질문 재입력 시 첫 토큰 응답 시간(TTFT)을 기존 4.0~8.0초에서 **100ms 미만(98% 이상 단축)**으로 개선.
* **SC-002 (GPU 컴퓨팅 부하 제거)**: 캐시 히트된 질의의 경우 모델 게이트웨이의 GPU 점유 시간 및 슬롯 획득 횟수 **0건 (100% GPU 오프로드)**.
* **SC-003 (사용자 체감 타이핑 UX 보존)**: 캐시 히트 시에도 자연스러운 스트리밍 Replay를 통해 UI 타이핑 애니메이션 오류 발생률 **0.0%**.
* **SC-004 (RAG 데이터 무결성 100%)**: 검색된 문서 내용/ID가 변경되었을 때 과거 캐시가 잘못 반환되는 Stale 응답 발생률 **0.0%**.
* **SC-005 (시스템 회복 탄력성)**: Redis 장애 발생 시 서비스 장애(500 에러) 0건 및 100% 자동 Fallback 수행.

---

## 5. Assumptions & Dependencies

* **인프라**: 기구축된 Redis 7.2 인스턴스(`aiservice-redis:6379`)를 공유하며, L1~L4 캐시 인프라(`redis_pool.py`)를 확장하여 사용한다.
* **LLM 단일성**: 현재 서빙 중인 단일 LLM 모델(`qwen3.5-2b`) 환경을 기본으로 하되, 다중 모델 확장 시 `model_id`가 캐시 키에 자동 반영된다.
* **대화 세션 독립성**: 이전 대화 히스토리(멀티턴)가 존재하는 경우, 직전 대화 맥락이 질문에 결합된 Rewrite 쿼리 또는 세션 컨텍스트를 캐시 키 해시에 포함한다.
