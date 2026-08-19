# Tasks: 018-llm-server-refactoring-optimization (2026 최신 트렌드 기반 LLM 서빙 게이트웨이 현대화 및 추론 성능 최적화)

**Input**: Design documents from `specs/018-llm-server-refactoring-optimization/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)
**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `- [ ] [TaskID] [P?] [Story?] Description with file path`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., [US1], [US2], [US3], [US4])

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize unit and benchmark test files for modern LLM engine optimizations

- [X] T001 Create unit test file `tests/unit/test_engine_optimization_flags.py` for FlashAttention, KV quantization, and prefix caching flags
- [X] T002 Create integration benchmark test `tests/integration/test_ttft_prefix_caching_benchmark.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core engine abstraction and configuration profiles that all stories depend on

**⚠️ CRITICAL**: Must complete before user story integrations begin

- [X] T003 Implement `BaseInferenceEngine` abstract class in `model_gateway/src/core/base_engine.py`
- [X] T004 Update `model_catalog.json` and `model_context_profiles.json` in `model_gateway/config/` for 2B (16K context, 8K max tokens) and 4B (12K context, 4K max tokens)

**Checkpoint**: Foundation ready - user story implementation can proceed in parallel

---

## Phase 3: User Story 1 - RAG 초저지연 첫 토큰(TTFT) 및 16K/12K 컨텍스트 최적화 (Priority: P1) 🎯 MVP

**Goal**: FlashAttention, KV Cache Q8_0 양자화, Prefix Caching, Chunked Prefill 플래그를 주입하여 TTFT 40% 단축 달성.

**Independent Test**: `tests/integration/test_ttft_prefix_caching_benchmark.py` passes and 2nd query TTFT < 350ms.

### Tests for User Story 1 (TDD)
- [X] T005 [P] [US1] Create unit tests for KV Cache calculation and VRAM budgeting in `tests/unit/test_kv_cache_vram_estimator.py`

### Implementation for User Story 1
- [X] T006 [US1] Inject `-fa`, `--cache-prompt`, `-ctk q8_0`, `-ctv q8_0`, `-b 512`, `-ub 256` into `process_manager.py` in `model_gateway/src/core/process_manager.py`
- [X] T007 [US1] Update VRAM limit estimator and GQA KV cache calculator in `model_gateway/src/core/process_manager.py`

**Checkpoint**: User Story 1 (MVP) is fully functional and testable independently.

---

## Phase 4: User Story 2 - 모듈형 추론 엔진 아키텍처 리팩토링 및 핫스왑 (Priority: P1)

**Goal**: `LlamaCppEngineAdapter` 모듈화 및 0.3초 웜 스와핑 / 10분 유휴 복귀 워치독 안정화.

**Independent Test**: Model hot-swaps between 2B and 4B in < 0.5s without VRAM memory leaks.

### Implementation for User Story 2
- [X] T008 [P] [US2] Implement `LlamaCppEngineAdapter` subclassing `BaseInferenceEngine` in `model_gateway/src/core/llama_engine_adapter.py`
- [X] T009 [P] [US2] Integrate `InferenceEngineFactory` and refactor `llama_manager.py` in `model_gateway/src/core/llama_manager.py`
- [X] T010 [US2] Verify 0.3s hot-swap and 10-minute idle fallback behavior in `model_gateway/src/core/process_manager.py`

**Checkpoint**: User Stories 1 AND 2 are fully functional and integrated.

---

## Phase 5: User Story 3 & 4 - 구조화된 JSON 제약 디코딩 및 실시간 관측성 (Priority: P2)

**Goal**: BNF JSON 스키마 제약 디코딩 보장 및 Prometheus `/metrics` 엔드포인트 실시간 연동.

**Independent Test**: 100 PILOS JSON reports generated with 0% parsing errors; `/metrics` exposes real-time TTFT and VRAM.

### Implementation for User Story 3 & 4
- [X] T011 [P] [US3] Enhance `parse_response_format` in `model_gateway/src/api/routes/inference_api.py` for guided JSON schema decoding
- [X] T012 [P] [US4] Implement Prometheus metrics exporter and real-time dashboard feed in `model_gateway/src/api/routes/health_api.py` and `dashboard_api.py`

**Checkpoint**: All 4 User Stories are fully functional across the gateway.

---

## Phase 6: Polish & Cross-Cutting Verification

**Purpose**: System-wide regression verification across ChatA, ChatB, PILOS Web, and PILOS Worker

- [X] T013 [P] Run full unit test suite across `model_gateway/tests/` and new test files
- [X] T014 Execute end-to-end RAG benchmark query on `model_gateway` and verify TTFT under 350ms
- [X] T015 Verify live container restart and gateway reload on `docker-compose.yml`

---

## Dependencies & Execution Order

### Phase Dependencies
- **Phase 1 (Setup)**: Can start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1 completion (BLOCKS all User Stories).
- **Phase 3 (User Story 1 - MVP)**: Depends on Phase 2.
- **Phase 4 (User Story 2)**: Depends on Phase 2.
- **Phase 5 (User Story 3 & 4)**: Depends on Phase 2 & Phase 3.
- **Phase 6 (Polish)**: Depends on all User Stories completion.
