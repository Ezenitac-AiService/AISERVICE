# Tasks: 017-korean-markdown-prompt-optimization (한국어 마크다운 볼드 렌더링 최적화 및 프롬프트 고도화)

**Input**: Design documents from `specs/017-korean-markdown-prompt-optimization/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)
**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `- [ ] [TaskID] [P?] [Story?] Description with file path`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., [US1], [US2], [US3])

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize test file for Korean markdown normalization

- [X] T001 Create unit test file `tests/unit/test_korean_markdown_sanitizer.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core sanitization utility and prompt safety rules that all stories depend on

**⚠️ CRITICAL**: Must complete before user story integrations begin

- [X] T002 Implement `normalize_korean_markdown()` regex sanitizer in `bteam/oliview_core/sanitizer.py`
- [X] T003 Implement Markdown Safety Rules in system prompt templates in `bteam/oliview_core/pipeline.py`

**Checkpoint**: Foundation ready - user story implementation can proceed in parallel

---

## Phase 3: User Story 1 - Clean Korean Markdown Bold & Quoting UX (Priority: P1) 🎯 MVP

**Goal**: Eliminate raw asterisk leaks (`**"..."**조사`) and ensure 100% clean bold/quote rendering in Oliview ChatA.

**Independent Test**: Unit test `tests/unit/test_korean_markdown_sanitizer.py` passes and pipeline test generates zero raw asterisks.

### Tests for User Story 1 (TDD)
- [X] T004 [P] [US1] Create unit tests for Korean markdown normalization vectors in `tests/unit/test_korean_markdown_sanitizer.py`

### Implementation for User Story 1
- [X] T005 [US1] Integrate `normalize_korean_markdown()` into LLM token streaming pipeline in `bteam/oliview_core/pipeline.py`
- [X] T006 [US1] Integrate `normalize_korean_markdown()` into Streamlit chat rendering in `bteam/Oliview_chatbot_a/app.py`, `06.02.app.py`, `06.app.py`

**Checkpoint**: User Story 1 (MVP) is fully functional and testable independently.

---

## Phase 4: User Story 2 - Prompt Engineering Standardization (Priority: P1)

**Goal**: Standardize Korean Markdown Safety Rules across all AI service prompts (ChatB, PILOS).

**Independent Test**: Prompt templates generate `- **라벨:** "인용문"` structured lists.

### Implementation for User Story 2
- [X] T007 [P] [US2] Update ChatB prompt in `bteam/Oliview_chatbot_b/common.py` with Korean Markdown Safety Rules
- [X] T008 [P] [US2] Update PILOS LLM prompt in `ateam/pilos-sentiment-index/pilos/llm/` with Korean Markdown Safety Rules

**Checkpoint**: User Stories 1 AND 2 are fully functional and integrated.

---

## Phase 5: User Story 3 - Frontend CJK Markdown Parser Guards (Priority: P2)

**Goal**: Provide client-side defensive parsing in Vanilla JS frontends (PILOS `chat.js`, ChatB web).

**Independent Test**: Browser rendering handles raw delimiter collision strings cleanly without visual breakages.

### Implementation for User Story 3
- [X] T009 [P] [US3] Implement CJK right-flanking delimiter sanitizer in `ateam/pilos-sentiment-index/pilos/web/static/js/chat.js`
- [X] T010 [P] [US3] Verify client-side markdown sanitization in ChatB web interface

**Checkpoint**: All 3 User Stories are fully functional across all frontends.

---

## Phase 6: Polish & Cross-Cutting Verification

**Purpose**: System-wide regression verification and live browser validation

- [X] T011 [P] Run full unit test suite `tests/unit/test_korean_markdown_sanitizer.py`
- [X] T012 Execute live RAG pipeline response validation on `식물나라 토너 자극성과 기능/효과 분석해줘`
- [X] T013 Verify live browser rendering on `https://ezenitac.duckdns.org/bteam/chata/`

---

## Dependencies & Execution Order

### Phase Dependencies
- **Phase 1 (Setup)**: Can start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1 completion (BLOCKS all User Stories).
- **Phase 3 (User Story 1 - MVP)**: Depends on Phase 2.
- **Phase 4 (User Story 2)**: Depends on Phase 2.
- **Phase 5 (User Story 3)**: Depends on Phase 2 & Phase 3.
- **Phase 6 (Polish)**: Depends on all User Stories completion.

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Phase 1 (Setup) + Phase 2 (Foundational).
2. Complete Phase 3 (User Story 1): Implement `normalize_korean_markdown()` and integrate into ChatA.
3. Validate User Story 1 independently with `tests/unit/test_korean_markdown_sanitizer.py`.
