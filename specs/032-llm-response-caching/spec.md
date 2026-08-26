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

### 1.2 2026년 8월 최신 업계 트렌드 및 프로덕션 방어 아키텍처

2026년 프로덕션 LLM 및 RAG 서빙 생태계(vLLM, SGLang Router, LiteLLM, Redis AI Gateway)의 응답 캐시 최적화 표준은 다음과 같습니다:

```
[2026 LLM Caching Hierarchy & Production Guardrails]
┌─────────────────────────────────────────────────────────────┐
│ Level 1: Exact-Match Key-Value Cache (Redis)                │  <-- 본 명세 타겟 (L5)
│  - Hashing: NFKC(Query) + DocIDs + PromptVer + Tenant       │  - 지연시간: < 10ms
│  - Guardrails: SingleFlight Lock, TTL Jitter (12h ± 1h)     │  - 방어: Poisoning Deny-List
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
2. **Multi-turn Contextual Query & Unicode Normalization (맥락 왜곡 방지)**:
   * 멀티턴 대화의 대명사 질의("이거 얼마야?", "다른 색상은?")가 이전 대화와 엉뚱한 제품으로 오염(Contamination)되지 않도록, `QueryRewriterNode`가 탈맥락화(Decontextualized)한 독립 질의를 기반으로 캐시 키를 생성합니다.
   * Unicode NFKC 정규화, 연속 공백 단일화, 소문자화 전처리를 통해 불필요한 캐시 미스를 방지하고 적중률을 극대화합니다.
3. **Context-Aware Cache Invalidation (RAG 데이터 무결성 보장)**:
   * 캐시 키에 `(정제 질의 + 상위 N개 문서 ID들의 정렬 해시 + 프롬프트 버전 + 모델 ID + 테넌트 ID)`를 조합하여, 리뷰 크롤링 및 감정 분석 배치가 돌아 DB 검색 문서가 바뀌면 **자동으로 캐시 미스가 발생하여 최신 정보를 반영**합니다.
4. **Cache Stampede 방지 (SingleFlight Lock & TTL Jitter)**:
   * 인기 질문의 캐시 만료 시점에 동시 다발 요청이 유입될 때 GPU 큐가 폭파되는 현상을 막기 위해, Redis 분산 락(`SingleFlightLock`)으로 1개 요청만 GPU 추론을 수행하고 나머지는 대기 후 공유합니다.
   * 12시간 기본 TTL에 무작위 Jitter(±1시간)를 적용하여 대량 키의 동시 만료를 방지합니다.
5. **Cache Poisoning 차단 (안전성 Deny-List Policy)**:
   * 가드레일 거부 응답, 프롬프트 인젝션 의심 질의, 에러성 문구, 20자 미만의 불완전 답변은 절대로 L5 캐시에 적재하지 않는 필터링 가드를 탑재합니다.
6. **Word-Boundary Streaming Cache Replay (UX 호환성 유지)**:
   * 캐시 히트 시 JSON 덤프 대신 **단어 단위(Word-Boundary, 4~10자 / 20~30ms 간격)의 고속 분할 스트리밍**으로 Replay하여 프론트엔드(Chat A, Chat B)의 SSE 파서 및 타이핑 애니메이션과 100% 호환되도록 합니다.

---

## Clarifications

### Session 2026-08-26 (Initial Clarification)
- **Q**: 리뷰 수집 및 감정 분석 갱신 주기를 반영한 L5 LLM 응답 캐시의 생명주기(TTL) 및 무효화(Invalidation) 정책을 어떻게 구성할까요?  
  **A**: **Option A 채택 (배치 주기 연동 TTL 12~24시간 + RAG 검색 문서 해시 기반 자동 무효화)** — 크롤러/분석 배치가 실행되어 상위 검색 리뷰나 평점이 바뀌면 검색 노드가 반환하는 `doc_ids_hash`가 변경되어 즉시 자동 캐시 미스 발생. 배치 작업 주기가 도래하지 않아 데이터 변경이 없을 때는 12~24시간(`redis_ttl_llm_response = 43200`초 기본값) 동안 안정적으로 캐시 히트(0 GPU)를 재사용한다.
- **Q**: L5 캐시 히트 시 클라이언트에 전달하는 스트리밍 반환 방식(Streaming Cache Replay)을 어떻게 구현할까요?  
  **A**: **Option A 채택 (고속 스트리밍 Replay)** — 청크당 20~30ms 간격으로 단어 단위 고속 분할 스트리밍하여 프론트엔드 UI(Chat A, Chat B)의 SSE 파서, 마크다운 렌더러 및 타이핑 애니메이션과 100% 호환되며 체감 지연 없이 매끄러운 UX를 보장한다.

### Session 2026-08-26 (Adversarial Multi-Persona Review)
- **Q**: 공격적 비판론자(분산 캐시 아키텍트, RAG 데이터 엔지니어, SRE 보안, 프론트 UX) 분석에서 도출된 5대 심층 보완 조치를 어떻게 반영할까요?  
  **A**: **5대 심층 조치 전면 수용 (M1~M5)**:
  1. `SingleFlightLock` 분산 락 및 `TTL Jitter(12h ± 1h)` 도입으로 Cache Stampede 방지.
  2. `QueryRewriterNode`의 탈맥락화 질의 및 Unicode NFKC 정규화 적용으로 멀티턴 맥락 왜곡 방지 및 캐시 적중률 제고.
  3. 에러 답변, 인젝션 거부 문구, 20자 미만 불완전 답변에 대한 Cache Poisoning Deny-List 가드레일 적용.
  4. 테넌트 간 데이터 격리 네임스페이스(`olliview:l5:{tenant}:{hash}`) 적용.
  5. 단어 경계(Word-Boundary) Replay 및 `x-cache: HIT` 메타데이터 전송으로 브라우저 렌더링 과부하 방지 및 관측성 확보.

---

## 2. User Scenarios & Testing *(mandatory)*

### User Story 1 - 동일 질문에 대한 초고속 LLM 캐시 응답 (Priority: P1) 🎯 MVP

사용자가 이전에 처리된 적이 있는 완전히 동일한 제품/비교 질문을 다시 입력했을 때, 시스템은 GPU 추론을 다시 실행하지 않고 Redis L5 캐시에서 즉시 응답을 인출하여 0.1초 이내에 단어 단위로 매끄럽게 스트리밍 답변을 제공합니다.

* **Why this priority**: 동일 질문 반복 인입 시 GPU 병목을 완전히 제거하고 사용자 응답 속도를 극대화하는 핵심 가치입니다.
* **Independent Test**: Chat A 또는 Chat B에서 "차앤박 프로폴리스 앰플 장점 알려줘"를 1회 질의하여 캐시를 생성한 후, 동일 질문을 재질의했을 때 게이트웨이 GPU 슬롯을 점유하지 않고 50ms 이내에 응답 스트리밍이 개시되는지 검증.
* **Acceptance Scenarios**:
  1. **Given** 과거에 처리되어 Redis L5 캐시에 저장된 질문과 검색 컨텍스트가 존재할 때, **When** 사용자가 동일한 질문을 전송하면, **Then** 모델 게이트웨이에 GPU 추론 요청을 보내지 않고 Redis 캐시에서 즉시 스트림을 생성하여 반환해야 한다.
  2. **Given** 캐시 히트된 응답이 전송될 때, **When** 클라이언트가 SSE 스트림을 수신하면, **Then** 단어 단위(20~30ms 간격)의 청크 포맷으로 스트리밍되어 UI 타이핑 애니메이션이 자연스럽게 작동해야 한다.
  3. **Given** 캐시가 적용된 상태에서, **When** 백엔드 처리 지연 시간을 측정하면, **Then** 첫 토큰 응답 시간(TTFT)이 50ms 미만이어야 한다.

---

### User Story 2 - RAG 컨텍스트 갱신 및 멀티턴 맥락 무결성 보장 (Priority: P2)

올리뷰의 리뷰 크롤링 및 감정 분석 배치가 돌아 제품 데이터가 갱신되었거나 사용자가 멀티턴 대명사 질의("이거 얼마야?")를 입력했을 때, 오래된 캐시나 엉뚱한 제품의 캐시가 반환되지 않고 정확한 최신 LLM 답변을 재생성합니다.

* **Why this priority**: 이커머스 추천 챗봇에서 가격, 품절 여부, 신규 리뷰 등의 최신 데이터 무결성 및 대화 맥락 정확성을 보장하기 위함입니다.
* **Independent Test**: 1턴에서 "헤라 블랙쿠션"을 묻고 2턴에서 "이거 지속력 어때?"를 물었을 때, 이전 롬앤 쿠션의 캐시와 충돌하지 않고 헤라 쿠션에 대한 정확한 답변이 생성되는지 검증.
* **Acceptance Scenarios**:
  1. **Given** 멀티턴 대화가 진행 중일 때, **When** 대명사 질의가 인입되면, **Then** 탈맥락화된 독립 질의(Rewritten Query)를 기준으로 L5 캐시 키를 생성하여 맥락 오염을 방지해야 한다.
  2. **Given** 특정 질문에 대한 캐시가 존재하는 상태에서, **When** 검색 노드가 반환한 상위 문서(Top-K Documents)의 ID 조합이 변경되면, **Then** 캐시 키가 달라져 캐시 미스로 판정되고 신규 LLM 생성이 트리거되어야 한다.

---

### User Story 3 - Cache Stampede 방지 및 안전성 가드레일 (Priority: P3)

인기 질문의 캐시가 만료되는 순간 다수의 동시 요청이 들어오더라도 GPU 큐가 폭파되지 않고 안전하게 동시성을 제어하며, 비정상 에러 답변이 캐시에 오염되지 않도록 보호합니다.

* **Why this priority**: 프로덕션 운영 환경에서의 대규모 트래픽 스파이크 방어 및 데이터 품질을 유지하기 위함입니다.
* **Independent Test**: 동일한 인기 질문 5개를 동시에 인입시켰을 때 SingleFlight 분산 락에 의해 단 1개의 GPU 추론만 실행되고 나머지는 캐시를 안전하게 공유하는지 검증.
* **Acceptance Scenarios**:
  1. **Given** 캐시가 만료된 인기 질의에 5개의 동시 요청이 유입될 때, **When** SingleFlight 락이 활성화되면, **Then** 1개의 요청만 GPU 추론을 실행하고 나머지 4개는 캐시 생성 대기 후 재사용해야 한다.
  2. **Given** 모델이 20자 미만의 오류 메시지나 안전성 거부 문구를 반환하면, **When** 응답이 종료되더라도, **Then** L5 캐시에 저장되지 않고 즉시 폐기되어야 한다.

---

### Edge Cases
* **스트리밍 도중 클라이언트 연결 끊김**: LLM이 답변을 생성하는 도중 클라이언트가 탭을 닫아도, 백그라운드에서 생성이 온전히 완료되고 최소 길이(>20자)를 만족한 경우에만 Redis에 L5 캐시로 커밋하여 불완전한(Truncated) 답변이 캐싱되지 않도록 방지.
* **빈 답변 또는 에러/거부 응답**: LLM 엔진이 에러 메시지나 "답변을 생성할 수 없습니다"와 같은 거부 문구를 반환한 경우 절대로 Redis에 캐싱하지 않음(Deny-List).
* **Redis 연결 일시 장애(Fail-Fast)**: Redis 서버가 다운되거나 타임아웃(0.2초) 발생 시, 에러를 내지 않고 캐시 미스로 안전하게 Fallback하여 GPU 추론을 직접 수행.
* **동시 유입 캐시 스탬피드**: SingleFlightLock 및 TTL Jitter(12h ± 1h)로 분산 처리.

---

## 3. Requirements *(mandatory)*

### Functional Requirements

* **FR-001 (L5 Exact LLM Response Cache Key with Normalization)**: `bteam/oliview_core`는 탈맥락화된 질문 텍스트(`rewritten_query`에 대해 Unicode NFKC 정규화, 연속 공백 단일화, 구두점 정리 적용), 리랭킹된 상위 문서 ID 목록의 정렬 해시(`doc_ids_hash`), 모델 식별자(`model_id`), 프롬프트 템플릿 버전 해시(`prompt_version_hash`), 테넌트 ID(`tenant_id`)를 조합하여 SHA-256 해싱하고 `olliview:l5:{tenant_id}:{hash}` 포맷의 고유 캐시 키를 생성해야 한다.
* **FR-002 (Synthesis Node L5 Cache Lookup)**: `synthesis_node.py` 및 `graph_orchestrator.py`는 LLM 생성 호출(`client.generate_stream`) 전에 L5 캐시를 우선 조회하여, 캐시 히트 시 GPU 게이트웨이 호출 없이 캐시된 응답을 즉시 반환해야 한다.
* **FR-003 (Word-Boundary Streaming Replay Engine)**: 캐시 히트 시, 캐시된 전체 텍스트를 클라이언트의 SSE 파서 및 브라우저 DOM 렌더링 최적화를 위해 단어 경계 단위(Word-Boundary, 청크당 4~10자 / 20~30ms 간격)로 고속 분할 재생(Replay)하여 전송해야 한다.
* **FR-004 (Cache Poisoning Deny-List Guard)**: LLM 스트리밍 응답이 정상 종료(`[DONE]`)되고, 완성된 텍스트의 길이가 20자 이상이며, 에러 문구 또는 안전성 거부 문구가 포함되지 않은 정상 답변만 Redis L5 캐시에 저장해야 한다.
* **FR-005 (Redis L5 TTL & Jitter Policy)**: L5 LLM 응답 캐시의 TTL 기본값은 12시간(`redis_ttl_llm_response = 43200`초)에 무작위 Jitter(±3600초)를 부여하여 대량 동시 만료를 방지해야 한다.
* **FR-006 (Context Invalidation)**: RAG 검색 풀 또는 리랭커 결과의 문서 조합이 단 하나라도 달라지면 캐시 키 해시가 변경되어 자동으로 최신 LLM 추론을 수행해야 한다.
* **FR-007 (SingleFlight Stampede Protection)**: 캐시 미스 시 동일 캐시 키에 대해 Redis 분산 락(`SingleFlightLock`)을 획득하여 단 1개의 요청만 GPU 추론을 수행하고, 동시 유입된 다른 요청은 대기 후 생성된 캐시를 구독하도록 제어해야 한다.
* **FR-008 (Fail-Fast Redis Fallback)**: Redis 소켓 타임아웃(0.2초) 초과 또는 연결 오류 발생 시 파이프라인 중단 없이 즉시 캐시 미스로 우회하여 GPU 추론을 정상 진행해야 한다.
* **FR-009 (Tenant-Aware Namespace Isolation)**: `chata`와 `chatb` 테넌트 간 캐시 키를 네임스페이스 레벨에서 엄격히 분리하여 교차 데이터 오염을 방지해야 한다.
* **FR-010 (Cache Bypass Support)**: 클라이언트 요청 헤더에 `Cache-Control: no-cache` 또는 `X-Bypass-Cache: true`가 명시된 경우 L5 캐시 조회를 건너뛰고 GPU 추론을 직접 트리거해야 한다.
* **FR-011 (Cache Metrics & Observability Header)**: L5 캐시 히트 시 SSE 스트림의 초기 메타데이터 또는 로그에 `is_cached: true`, `x-cache: HIT`, 절감된 GPU 지연 시간(`latency_saved_s`)을 기록하여 관측 가능성을 보장해야 한다.

---

### Key Entities

* **`L5ResponseCachePayload`**: Redis에 직렬화되어 저장되는 완성된 LLM 응답 데이터 구조체.
  * 속성: `response_text` (완성된 답변 텍스트), `model_id`, `created_at` (타임스탬프), `doc_ids` (참조된 문서 ID 목록), `prompt_version`, `tenant_id`.
* **`CacheReplayStream`**: 캐시된 응답을 실시간 SSE 스트림 형식으로 변환하는 비동기 제너레이터.
  * 속성: `chunk_size` (단어 단위), `interval_ms` (20~30ms), `is_cached: True`.

---

## 4. Success Criteria *(mandatory)*

### Measurable Outcomes

* **SC-001 (동일 질의 첫 토큰 응답 속도 단축)**: 동일 질문 재입력 시 첫 토큰 응답 시간(TTFT)을 기존 4.0~8.0초에서 **50ms 미만(99% 이상 단축)**으로 개선.
* **SC-002 (GPU 컴퓨팅 부하 제거)**: 캐시 히트된 질의의 경우 모델 게이트웨이의 GPU 점유 시간 및 슬롯 획득 횟수 **0건 (100% GPU 오프로드)**.
* **SC-003 (사용자 체감 타이핑 UX 보존)**: 단어 단위 고속 스트리밍 Replay를 통해 브라우저 프리징 0건 및 자연스러운 타이핑 애니메이션 제공.
* **SC-004 (RAG 데이터 무결성 & 멀티턴 맥락 보존 100%)**: 검색된 문서 변경 시 Stale 응답 0건 및 멀티턴 대명사 질의 맥락 오염 발생률 **0.0%**.
* **SC-005 (시스템 회복 탄력성 & 스탬피드 방어)**: 동시 다발 캐시 만료 시 GPU 부하 스파이크 0건 및 Redis 장애 시 100% 자동 Fallback 수행.

---

## 5. Assumptions & Dependencies

* **인프라**: 기구축된 Redis 7.2 인스턴스(`aiservice-redis:6379`)를 공유하며, L1~L4 캐시 인프라(`redis_pool.py`)를 확장하여 사용한다.
* **LLM 단일성**: 현재 서빙 중인 단일 LLM 모델(`qwen3.5-2b`) 환경을 기본으로 하되, 다중 모델 확장 시 `model_id`가 캐시 키에 자동 반영된다.
* **Query Rewriter**: 멀티턴 대화의 대명사 및 문맥 복원은 RAG 파이프라인의 `QueryRewriterNode` 결과를 활용한다.
