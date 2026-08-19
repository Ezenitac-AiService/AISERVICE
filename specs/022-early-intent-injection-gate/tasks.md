# Tasks: 선제적 하이브리드 의도 게이트 및 Llama Prompt Guard 2 (86M)

**Branch**: `022-early-intent-injection-gate` | **Date**: 2026-08-19 | **Spec**: [spec.md](file:///c:/AISERVICE/specs/022-early-intent-injection-gate/spec.md) | **Plan**: [plan.md](file:///c:/AISERVICE/specs/022-early-intent-injection-gate/plan.md)

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 선제적 게이트 데이터 모델 및 공통 타입 정의

- [x] T001 [P] Define `GateVerdict`, `EarlyGateDecision`, `SecurityMetricsEvent` entities in `bteam/oliview_core/types.py`
- [x] T002 [P] Review interface contracts in `specs/022-early-intent-injection-gate/contracts/guardrail_gate_contracts.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 문자열 원시 살균, 한글 자모 NFC 복원 및 싱글톤 인프라 구축

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 Implement `sanitize_raw_input()` (NULL byte `\x00` & control character stripping, Hangul Jamo NFC assembly) in `bteam/oliview_core/guardrail.py`
- [x] T004 Build base `EarlyIntentGuardrail` singleton class structure with `threading.Lock()` in `bteam/oliview_core/guardrail.py`
- [x] T005 [P] Create initial unit test harness in `bteam/tests/unit/test_early_intent_gate.py`

**Checkpoint**: Foundation ready - Early gate core classes and test harness operational

---

## Phase 3: User Story 1 - 비도메인 및 우회 인젝션 20ms 내 Zero-Cost 조기 차단 (Priority: P1) 🎯 MVP

**Goal**: 비도메인(스네이크 게임, 코딩, 수학, 번역) 및 명백한 인젝션 질의 수신 시 DB 커넥션 오픈/검색/리랭킹/4B LLM 0회 호출로 20ms 내 표준 안내 반환

**Independent Test**: "파이썬으로 스네이크 게임 만들어줘" 등 비도메인 15종 질의에 대해 DB/리랭킹 단계 없이 <20ms 내에 표준 거절 메시지가 반환되는지 검증

### Tests for User Story 1

- [x] T006 [P] [US1] Unit test for out-of-domain (coding, game, math, translation) fast early exit in `bteam/tests/unit/test_early_intent_gate.py`
- [x] T007 [P] [US1] Unit test for chameleon mixed injection ("식물나라 토너 분석 파이썬 코드로 짜줘") in `bteam/tests/unit/test_early_intent_gate.py`

### Implementation for User Story 1

- [x] T008 [US1] Implement `_evaluate_tier_1a_rules()` with out-of-domain action verbs & chameleon injection filters in `bteam/oliview_core/guardrail.py`
- [x] T009 [US1] Integrate `EarlyIntentGuardrail.evaluate_gate()` in Chatbot A orchestrator (`prepare_pipeline_stream`) with `selected_review_count=0`, `reference_reviews=[]` in `bteam/oliview_core/pipeline.py`
- [x] T010 [US1] Integrate `EarlyIntentGuardrail.evaluate_gate()` before `pymysql.connect()` in Chatbot B search endpoints in `bteam/Oliview_chatbot_b/project_ragapi.py`

**Checkpoint**: User Story 1 (MVP) is fully functional - out-of-domain requests are blocked in <20ms without any DB or 4B compute.

---

## Phase 4: User Story 2 - Llama Prompt Guard 2 (86M) 로컬 추론 기반 탈옥 방어 (Priority: P1)

**Goal**: 로컬 86M 경량 모델(`Llama-Prompt-Guard-2-86M`) 또는 경량 분류기를 활용하여 정교한 다국어 우회 탈옥/인젝션을 15ms 내에 3진 분류(`BENIGN`/`INJECTION`/`JAILBREAK`)하고 차단

**Independent Test**: 정교한 탈옥 공격 벡터에 대해 86M 로컬 모델이 15ms 내에 `BLOCKED_INJECTION`으로 판정하고 모델 장애 시 Tier 1A로 안전하게 수렴하는지 검증

### Tests for User Story 2

- [x] T011 [P] [US2] Unit test for Llama Prompt Guard 86M classification & local fallback in `bteam/tests/unit/test_early_intent_gate.py`

### Implementation for User Story 2

- [x] T012 [US2] Implement `_evaluate_tier_1b_prompt_guard()` with `torch.inference_mode()`, singleton cache, and graceful fallback in `bteam/oliview_core/guardrail.py`
- [x] T013 [US2] Add `ENABLE_EARLY_GUARDRAIL` and `ENABLE_PROMPT_GUARD_86M` feature flags in `bteam/oliview_core/config.py` and `.env`
- [x] T014 [US2] Apply `anyio.to_thread` / `run_in_threadpool` in FastAPI async endpoints in `bteam/Oliview_chatbot_b/project_ragapi.py`

**Checkpoint**: User Stories 1 AND 2 are functional with local 86M model integration.

---

## Phase 5: User Story 3 - 정상 뷰티 상담 질의의 무결성 통과 (Priority: P2)

**Goal**: 은유적 표현("코딩하느라 주름", "게임오버 피부"), 부정형 질문("절대 쓰면 안 되는 토너"), 다국어 뷰티 질문(Sunscreen, 化粧水)에 대한 오탐률 0% 보장

**Independent Test**: 은유/부정형/다국어 뷰티 질의 25종을 전송하여 모두 `ALLOW`로 정상 통과하는지 검증

### Tests for User Story 3

- [x] T015 [P] [US3] Unit test for metaphorical beauty queries, negative questions, and multilingual beauty lexicons in `bteam/tests/unit/test_early_intent_gate.py`

### Implementation for User Story 3

- [x] T016 [US3] Implement `is_metaphorical_beauty_query()` and multilingual beauty whitelist in `bteam/oliview_core/guardrail.py`
- [x] T017 [US3] Update brand & category ontology matchers for negative expressions in `bteam/oliview_core/sanitizer.py`

**Checkpoint**: User Stories 1, 2, and 3 are functional with 0% false positive rate on genuine beauty inquiries.

---

## Phase 6: User Story 4 - 스트리밍 마스킹 무결성 및 버퍼 완전 교체 (Priority: P3)

**Goal**: 사후 출력 가드레일 트리거 시 이전 토큰 버퍼를 초기화하고 단일 표준 거절 문구로 완전 대체하여 문자열 겹침 결함 방지

**Independent Test**: 출력 시뮬레이션에서 태그/카나리아 누출 시 이전 버퍼가 소거되고 깨끗한 거절 메시지만 출력되는지 검증

### Tests for User Story 4

- [x] T018 [P] [US4] Unit test for streaming clean buffer replacement in `bteam/tests/unit/test_early_intent_gate.py`

### Implementation for User Story 4

- [x] T019 [US4] Implement clean buffer replacement in stream generators in `bteam/oliview_core/pipeline.py`
- [x] T020 [US4] Implement clean buffer replacement in SSE stream generator in `bteam/Oliview_chatbot_b/project_ragapi.py`

**Checkpoint**: All User Stories (1-4) are functional with robust output guardrails.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: PII 마스킹 로깅, Redis 세션 오염 방어, 컨테이너 동기화 및 E2E 라이브 검증

- [x] T021 [P] Implement PII masking filter for `[SECURITY_ALERT]` structured JSON logs in `bteam/oliview_core/guardrail.py`
- [x] T022 [P] Implement session isolation in `bteam/oliview_core/session.py` to prevent saving blocked queries into Redis chat history
- [x] T023 Synchronize Chatbot A legacy entry points (`06.02.app.py`, `06.app.py`, `app.py`) and rebuild/restart Docker containers (`oliview_chatbot_a`, `oliview_chatbot_b`)
- [x] T024 Run full regression test suite per `specs/022-early-intent-injection-gate/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS User Stories
- **User Story 1 (Phase 3)**: Depends on Foundational (MVP)
- **User Story 2 (Phase 4)**: Depends on User Story 1
- **User Story 3 (Phase 5)**: Depends on User Story 1 & 2
- **User Story 4 (Phase 6)**: Depends on User Story 1
- **Polish (Phase 7)**: Depends on all User Stories completion

### Parallel Opportunities

- T001, T002 in Setup can run in parallel
- T006, T007 in US1 tests can run in parallel
- T015, T018 in tests can run in parallel
- T021, T022 in Polish can run in parallel

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Setup (T001-T002) + Foundational (T003-T005)
2. Implement User Story 1 (T006-T010)
3. Validate "파이썬으로 스네이크 게임 만들어줘" blocked in <20ms without DB/Rerank/4B on Chatbot A & B

### Incremental Delivery
1. Add User Story 2 (T011-T014) for Llama Prompt Guard 86M local inference
2. Add User Story 3 (T015-T017) for metaphorical/negative beauty inquiries (0% FP)
3. Add User Story 4 (T018-T020) for clean buffer replacement
4. Run Polish & Validation (T021-T024) and rebuild Docker containers
