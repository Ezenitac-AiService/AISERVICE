# Tasks: 016-system-codebase-refactoring (통합 시스템 코드베이스 리팩토링 및 아키텍처 현대화)

**Input**: Design documents from `specs/016-system-codebase-refactoring/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)
**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `- [ ] [TaskID] [P?] [Story?] Description with file path`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., [US1], [US2], [US3], [US4])

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize directory structure for `oliview_core` package and test hierarchy

- [X] T001 Create `bteam/oliview_core/` package directory structure per implementation plan
- [X] T002 [P] Create `tests/unit/` and `tests/integration/` directories for refactored test suites
- [X] T003 [P] Initialize `bteam/oliview_core/__init__.py` with package version and export manifest

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data schemas, configuration, and interfaces that all stories depend on

**⚠️ CRITICAL**: Must complete before user story implementations begin

- [X] T004 [P] Implement Pydantic & Dataclass schema models (`StepCode`, `StepEvent`, `ReferenceReview`, `RagExecutionMetadata`) in `bteam/oliview_core/types.py`
- [X] T005 [P] Implement centralized environment configuration loader (`CoreSettings`) in `bteam/oliview_core/config.py`
- [X] T006 [P] Implement `StepCallbackProtocol` and `StreamlitStepCallback` in `bteam/oliview_core/callback.py`
- [X] T007 [P] Implement MySQL connection factory and query helper functions in `bteam/oliview_core/db.py`

**Checkpoint**: Foundation ready - user story implementation can proceed in parallel

---

## Phase 3: User Story 1 - Standard `oliview_core` Package & Modular Pipeline (Priority: P1) 🎯 MVP

**Goal**: Transform sequential tutorial scripts into a standard modular RAG pipeline with 2-stage execution (`prepare_stream` + `generate_stream`).

**Independent Test**: Unit test `tests/unit/test_oliview_core_imports.py` and pipeline test `tests/integration/test_pipeline_e2e.py` pass without dynamic file loaders.

### Tests for User Story 1 (TDD)
- [X] T008 [P] [US1] Create unit tests for module imports and schema validation in `tests/unit/test_oliview_core_imports.py`
- [X] T009 [P] [US1] Create pipeline execution integration tests in `tests/integration/test_pipeline_e2e.py`

### Implementation for User Story 1
- [X] T010 [P] [US1] Implement text sanitizer, noise filtering, and Olive Young URL builder in `bteam/oliview_core/sanitizer.py`
- [X] T011 [P] [US1] Implement ChromaDB/Faiss vector store & BM25 sparse hybrid retrieval engine in `bteam/oliview_core/retrieval.py`
- [X] T012 [P] [US1] Implement high-speed GPU BGE-Reranker client (`port 8091`) with lazy CrossEncoder fallback in `bteam/oliview_core/rerank.py`
- [X] T013 [US1] Implement 2-stage RAG pipeline orchestrator (`prepare_pipeline_stream` & `generate_answer_stream`) in `bteam/oliview_core/pipeline.py`
- [X] T014 [US1] Build standardized Streamlit main application in `bteam/Oliview_chatbot_a/app.py` utilizing `oliview_core.pipeline`
- [X] T014a [P] [US1] Optimize 1-click example query button layout (column ratio `[1.6, 1.4]` and button auto-wrap CSS) in `bteam/Oliview_chatbot_a/app.py` and `06.02.app.py`

**Checkpoint**: User Story 1 (MVP) is fully functional and testable independently.

---

## Phase 4: User Story 2 - Dual Sync/Async `AiGatewayClient` & Connection Pooling (Priority: P1)

**Goal**: Provide a unified, thread-safe, and event-loop-safe AI client for LLM inference, BGE-M3 embeddings, and BGE-Reranker.

**Independent Test**: Unit test `tests/unit/test_ai_gateway_client.py` validates both sync methods (Streamlit) and async methods (FastAPI) without event loop errors.

### Tests for User Story 2 (TDD)
- [X] T015 [P] [US2] Create sync and async client unit tests in `tests/unit/test_ai_gateway_client.py`

### Implementation for User Story 2
- [X] T016 [US2] Implement synchronous HTTP client methods (`embed`, `rerank`, `generate_stream`) in `bteam/oliview_core/client.py`
- [X] T017 [US2] Implement asynchronous HTTP client methods (`aembed`, `arerank`, `agenerate_stream`) in `bteam/oliview_core/client.py`
- [X] T018 [US2] Integrate `AiGatewayClient` into `bteam/oliview_core/pipeline.py` and `bteam/oliview_core/retrieval.py`
- [X] T019 [US2] Update `bteam/Oliview_chatbot_b/project_ragapi.py` to utilize `oliview_core.client.AiGatewayClient` and `oliview_core.types`

**Checkpoint**: User Stories 1 AND 2 are fully functional and integrated.

---

## Phase 5: User Story 3 - Deprecation Shims & Legacy Script Archiving (Priority: P2)

**Goal**: Provide 100% backward compatibility for Docker entrypoints while safely archiving legacy sequential scripts.

**Independent Test**: Executing `streamlit run 06.02.app.py` or `06.app.py` succeeds by delegating to `app.py`.

### Implementation for User Story 3
- [X] T020 [P] [US3] Create `bteam/Oliview_chatbot_a/legacy_archive/` directory for historical reference
- [X] T021 [US3] Move legacy sequential scripts (`01.`, `02.`, `03.03.`, `05.01.`) into `bteam/Oliview_chatbot_a/legacy_archive/`
- [X] T022 [US3] Refactor `bteam/Oliview_chatbot_a/05.chatbot.py` into a thin backward-compatibility shim calling `oliview_core.pipeline`
- [X] T023 [US3] Refactor `bteam/Oliview_chatbot_a/06.02.app.py` into a backward-compatibility shim calling `app.py`
- [X] T024 [US3] Refactor `bteam/Oliview_chatbot_a/06.app.py` into a backward-compatibility shim calling `app.py`

**Checkpoint**: Legacy entrypoints delegate seamlessly without code duplication.

---

## Phase 6: User Story 4 - Unified Config Manager & Container Environment (Priority: P3)

**Goal**: Standardize environment variables and ensure container `PYTHONPATH` resolution for seamless Docker deployment.

**Independent Test**: Docker containers `oliview_chatbot_a` and `oliview_chatbot_b` restart and run with HTTP 200 without import errors.

### Implementation for User Story 4
- [X] T025 [P] [US4] Update `docker-compose.yml` to set `PYTHONPATH: /app:/bteam` and verify volume mounts for `oliview_chatbot_a` and `oliview_chatbot_b`
- [X] T026 [P] [US4] Update `.env` and `bteam/.env` to harmonize environment variable naming (`SERVER_HOST`, `MAIN_PORT`, `EMBED_PORT`, `RERANK_PORT`)
- [X] T027 [US4] Verify PILOS markdown renderer infinite loop safety guard in `ateam/pilos-sentiment-index/pilos/web/static/js/chat.js`
- [X] T028 [US4] Restart Docker containers `oliview_chatbot_a` and `oliview_chatbot_b` to verify clean startup logs

**Checkpoint**: Entire containerized system runs with standardized configurations.

---

## Phase 7: Polish & Cross-Cutting Verification

**Purpose**: System-wide regression verification and performance benchmarks

- [X] T029 [P] Run full pytest suite across `tests/unit/` and `tests/integration/`
- [X] T030 Execute live browser verification on `https://ezenitac.duckdns.org/bteam/chata/` (4-step status box, token streaming, accordion)
- [X] T031 Execute live browser verification on `https://ezenitac.duckdns.org/bteam/chatb/` (SSE streaming & filter chips)
- [X] T032 [P] Verify quickstart validation guide in `specs/016-system-codebase-refactoring/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies
- **Phase 1 (Setup)**: Can start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1 completion (BLOCKS all User Stories).
- **Phase 3 (User Story 1 - MVP)**: Depends on Phase 2.
- **Phase 4 (User Story 2)**: Depends on Phase 2 & Phase 3.
- **Phase 5 (User Story 3)**: Depends on Phase 3.
- **Phase 6 (User Story 4)**: Depends on Phase 3 & Phase 4.
- **Phase 7 (Polish)**: Depends on all User Stories completion.

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Phase 1 (Setup) + Phase 2 (Foundational).
2. Complete Phase 3 (User Story 1): Create `oliview_core` modules and `app.py`.
3. Validate User Story 1 independently with `tests/unit/test_oliview_core_imports.py` and `test_pipeline_e2e.py`.

### Incremental Delivery
1. Foundation & Core Pipeline (US1) -> Instant code quality improvement.
2. Dual AI Client (US2) -> ChatA & ChatB unified model connectivity.
3. Shims & Archival (US3) -> Zero docker breakage, clean codebase.
4. Container & Config (US4) -> Production deployment stability.
