# Tasks: 챗봇 A/B 런타임 오류 해결 및 vLLM 서빙 게이트웨이 OOM 방어·안정화

**Feature**: `024-chatbot-gateway-stability-fix`
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 챗봇 A/B 및 게이트웨이 안정성 테스트 하네스 구성

- [x] T001 [P] Review stability contracts in `specs/024-chatbot-gateway-stability-fix/contracts/stability_contracts.md`
- [x] T002 [P] Inspect `vllm-serv-gateway` process management and port 8089 healthcheck endpoints

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 챗봇 가드레일 및 재시도 정책 기반 모듈 구축

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 [P] Create initial unit test suite in `bteam/tests/unit/test_chatbot_stability.py` for `budget_context_documents()`
- [x] T004 Define common retry helper `safe_llm_call_with_retry()` in `bteam/Oliview_chatbot_a/llm_common.py`

**Checkpoint**: Foundation ready - unit test harness and retry decorator operational

---

## Phase 3: User Story 1 - 챗봇 B 정상 응답 및 변수 참조 무결성 확보 (Priority: P1) 🎯 MVP

**Goal**: `budget_context_documents()` 내 `is_9b` 변수 선언 누락으로 인한 `NameError`를 완전 제거하고 챗봇 B 정상 응답 보장

**Independent Test**: 챗봇 B에 복합 스킨케어 질의 전송 시 0개의 `NameError`로 100% 정상 맞춤 솔루션 수신

### Tests for User Story 1

- [x] T005 [P] [US1] Unit test for `budget_context_documents` in `bteam/Oliview_chatbot_b/common.py` with various `model_name` inputs

### Implementation for User Story 1

- [x] T006 [US1] Fix `budget_context_documents()` in `bteam/Oliview_chatbot_b/common.py` by declaring `is_9b = "9b" in str(model_name).lower()`
- [x] T007 [US1] Add 503/502 retry wrapper to `project_ragapi.py` in `bteam/Oliview_chatbot_b/project_ragapi.py`

**Checkpoint**: User Story 1 (MVP) complete - Chatbot B operates without any `NameError`

---

## Phase 4: User Story 2 - 챗봇 A 코드 무결성 및 LLM 통신 안정성 확보 (Priority: P1)

**Goal**: 챗봇 A의 `llm_common.py` 내 `is_9b` 변수 정의를 완비하고 LLM 503 오류 발생 시 자동 재시도 적용

**Independent Test**: 챗봇 A에 뷰티 질의 전송 시 503 에러 없이 2초 이내 정상 응답 렌더링

### Tests for User Story 2

- [x] T008 [P] [US2] Unit test for `budget_context_documents` in `bteam/Oliview_chatbot_a/llm_common.py`

### Implementation for User Story 2

- [x] T009 [US2] Fix `budget_context_documents()` in `bteam/Oliview_chatbot_a/llm_common.py` by declaring `is_9b = "9b" in str(model_name).lower()`
- [x] T010 [US2] Synchronize `bteam/oliview_core` with fixed `llm_common.py` and pipeline definitions

**Checkpoint**: User Stories 1 AND 2 complete - both Chatbots free of Python runtime errors

---

## Phase 5: User Story 3 - vLLM 서빙 게이트웨이 OOM 자가 치유 및 서브프로세스 복원 (Priority: P1)

**Goal**: 게이트웨이 `ProcessManager`가 서브프로세스 OOM/다운 감지 시 3초 이내 무중단 자동 재생성하여 503 장애 원천 방어

**Independent Test**: 서브프로세스 강제 종료 시 게이트웨이가 즉시 프로세스를 재생성하고 헬스체크 200 OK 복원

### Tests for User Story 3

- [x] T011 [P] [US3] Unit test for `ProcessManager.ensure_server_running()` subprocess recovery

### Implementation for User Story 3

- [x] T012 [US3] Enhance `model_gateway/src/process_manager.py` to auto-restart dead subprocesses (Exit Code -9 / 137) on route request
- [x] T013 [US3] Tune memory parameters and prompt cache safety in `model_gateway` to minimize OOM occurrence

**Checkpoint**: User Stories 1, 2, and 3 complete - Gateway self-heals from high load OOM spikes

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 컨테이너 재빌드, 실시간 챗봇 A/B 질의 E2E 검증 및 보고서 작성

- [x] T014 [P] Rebuild and restart `vllm-serv`, `oliview_chatbot_a`, and `oliview_chatbot_b` Docker containers
- [x] T015 Run live test queries on Chatbot A (`/bteam/chata/`) and Chatbot B (`/bteam/chatb/`) to assert 200 OK responses
- [x] T016 Run quickstart validation scenarios per `specs/024-chatbot-gateway-stability-fix/quickstart.md`
- [x] T017 Document walkthrough and create final verification report

---

## Dependencies & Execution Order

- **Phase 1 (Setup)** -> **Phase 2 (Foundational)** -> **Phase 3 (User Story 1 - MVP)** -> **Phase 4 (User Story 2)** -> **Phase 5 (User Story 3)** -> **Phase 6 (Polish)**
