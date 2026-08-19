# Tasks: Oliview Chatbot A/B 다계층 프롬프트 인젝션 방어 가드레일

**Branch**: `021-prompt-injection-defense-guardrails` | **Date**: 2026-08-19 | **Spec**: [spec.md](file:///c:/AISERVICE/specs/021-prompt-injection-defense-guardrails/spec.md) | **Plan**: [plan.md](file:///c:/AISERVICE/specs/021-prompt-injection-defense-guardrails/plan.md)

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 보안 가드레일 데이터 모델 및 계약 환경 초기화

- [x] T001 [P] Define security entities (`InjectionDetectionResult`, `SecurityEventLog`, `SandboxedPromptPayload`) in `bteam/oliview_core/types.py`
- [x] T002 [P] Review interface contracts and invariant rules in `specs/021-prompt-injection-defense-guardrails/contracts/guardrail_contracts.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 핵심 전처리(De-obfuscation) 및 시그니처 정규식 엔진 기반 구축

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 Implement Unicode normalization, zero-width space removal, and homoglyph de-obfuscation in `bteam/oliview_core/guardrail.py`
- [x] T004 Build ReDoS-safe precompiled regex threat signature patterns (Jailbreak, DAN, Prompt Leakage, System Override) in `bteam/oliview_core/guardrail.py`
- [x] T005 [P] Create initial unit test harness for prompt injection guardrails in `bteam/tests/unit/test_guardrail.py`

**Checkpoint**: Foundation ready - Tier 1 injection detection engine is testable and operational

---

## Phase 3: User Story 1 - 직접 프롬프트 인젝션 및 탈옥 시도 선제적 차단 (Priority: P1) 🎯 MVP

**Goal**: 사용자 직접 입력에서 탈옥, 시스템 프롬프트 유출, 지침 무시 공격을 100% 탐지하여 표준 거절 메시지를 반환하고 백엔드 LLM 호출 차단

**Independent Test**: 직접 인젝션 20종 공격 벡터를 전달했을 때 `is_blocked=True` 및 표준 안전 응답(`SAFE_BLOCKED_RESPONSE`)이 반환되는지 검증

### Tests for User Story 1

- [x] T006 [P] [US1] Unit test for direct injection, DAN jailbreak, and system prompt leakage attacks in `bteam/tests/unit/test_guardrail.py`
- [x] T007 [P] [US1] Unit test for cosmetic review legitimate questions (0% false positive) in `bteam/tests/unit/test_guardrail.py`

### Implementation for User Story 1

- [x] T008 [US1] Implement `detect_injection()` and `SAFE_BLOCKED_RESPONSE` in `bteam/oliview_core/guardrail.py`
- [x] T009 [US1] Integrate `PromptInjectionGuardrail.detect_injection()` in Chatbot A stream orchestrator in `bteam/oliview_core/pipeline.py`
- [x] T010 [US1] Integrate `PromptInjectionGuardrail.detect_injection()` in Chatbot B endpoints (`fast_chat`, `generate_llm_rag_answer`) in `bteam/Oliview_chatbot_b/project_ragapi.py`

**Checkpoint**: User Story 1 (MVP) is fully functional - both chatbots block direct prompt injection attempts before invoking the LLM.

---

## Phase 4: User Story 2 - RAG 검색 데이터 기반 간접 프롬프트 인젝션 무력화 (Priority: P2)

**Goal**: RAG 검색 데이터 및 사용자 입력을 XML 태그로 샌드박싱하고 태그 이스케이프 및 최하단 지시문 재배치(Instruction Defense) 적용

**Independent Test**: 오염된 악성 리뷰 텍스트가 RAG 컨텍스트에 주입되어도 LLM이 악성 명령을 무시하고 화장품 질문에만 정상 응답하는지 검증

### Tests for User Story 2

- [x] T011 [P] [US2] Unit test for XML tag sanitization, delimiter escaping, and indirect injection isolation in `bteam/tests/unit/test_guardrail.py`

### Implementation for User Story 2

- [x] T012 [US2] Implement `sanitize_xml_tags()` and `build_sandboxed_rag_prompt()` with Canary Token injection in `bteam/oliview_core/guardrail.py`
- [x] T013 [US2] Apply XML sandboxed prompt template and bottom instruction defense in `bteam/oliview_core/pipeline.py`
- [x] T014 [US2] Apply XML sandboxed prompt template and passive data isolation in `bteam/Oliview_chatbot_b/project_ragapi.py`

**Checkpoint**: User Stories 1 AND 2 are both functional - direct and indirect injections are completely neutralized.

---

## Phase 5: User Story 3 - 초저지연 보안 필터링 및 관측 가능성 (Priority: P3)

**Goal**: 가드레일 추가 지연시간을 10ms 이하로 유지하고, 카나리아 토큰 출력 검증 및 구조화된 보안 이벤트 JSON 로깅 구현

**Independent Test**: 100회 반복 질의 벤치마크에서 평균 지연시간 <10ms 달성 및 차단 이벤트 로그 기록 검증

### Tests for User Story 3

- [x] T015 [P] [US3] Latency benchmark test measuring <10ms execution time and output canary detection in `bteam/tests/unit/test_guardrail.py`
- [x] T016 [US3] Implement `verify_output_safety()` output guardrail in `bteam/oliview_core/guardrail.py`
- [x] T017 [US3] Implement structured JSON security event logging for blocked requests in `bteam/oliview_core/guardrail.py`
- [x] T018 [US3] Integrate output stream canary guardrail in `bteam/oliview_core/pipeline.py` and `bteam/Oliview_chatbot_b/project_ragapi.py`

**Checkpoint**: All three User Stories are fully functional with structured logging and sub-10ms performance.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 서비스 동기화, 컨테이너 배포 및 E2E 검증

- [x] T019 [P] Synchronize Chatbot A legacy entry points (`06.02.app.py`, `06.app.py`, `app.py`) in `bteam/Oliview_chatbot_a/`
- [x] T020 [P] Deploy and restart Docker containers (`oliview_chatbot_a`, `oliview_chatbot_b`) and verify health status
- [x] T021 Run full security regression test suite per `specs/021-prompt-injection-defense-guardrails/quickstart.md`
- [x] T022 Re-verify Spec Quality Checklist in `specs/021-prompt-injection-defense-guardrails/checklists/requirements.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS User Stories
- **User Story 1 (Phase 3)**: Depends on Foundational completion (MVP)
- **User Story 2 (Phase 4)**: Depends on User Story 1 completion
- **User Story 3 (Phase 5)**: Depends on User Story 2 completion
- **Polish (Phase 6)**: Depends on all User Stories completion

### Parallel Opportunities

- T001, T002 in Setup can run in parallel
- T006, T007 in US1 tests can run in parallel
- T019, T020 in Polish phase can run in parallel

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Setup (T001-T002) + Foundational (T003-T005)
2. Implement User Story 1 (T006-T010)
3. Validate direct injection blocking and zero false positive on Chatbot A/B

### Incremental Delivery
1. Add User Story 2 (T011-T014) for XML sandboxing and indirect injection defense
2. Add User Story 3 (T015-T018) for canary token output guardrail and sub-10ms benchmark
3. Run Polish & Validation (T019-T022) and deploy to Docker containers
