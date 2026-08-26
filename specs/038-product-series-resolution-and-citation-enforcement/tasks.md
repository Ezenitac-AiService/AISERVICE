# Tasks: 038-product-series-resolution-and-citation-enforcement (라인/시리즈명 모호성 해소, 화장품 부정 속성어 의미 왜곡 방지, 0건 환각 차단 및 ChatA FastAPI 2026 모바일 반응형 웹 전환)

**Branch**: `038-product-series-resolution-and-citation-enforcement`  
**Date**: 2026-08-26  
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

---

## Phase 1: Setup (Shared Infrastructure & Schemas)

**Purpose**: 프로젝트 기초 데이터 모델, 뷰티 부정 속성 사전 정의 및 공통 스키마 구축

- [ ] T001 [P] Create series matching and stream payload schemas in `bteam/Oliview_chatbot_a/oliview_core/models/series_models.py`
- [ ] T002 [P] Define `NEGATIVE_ASPECT_LEXICON` dictionary and polarity mapping in `bteam/Oliview_chatbot_a/oliview_core/models/aspect_lexicon.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 모든 User Story가 의존하는 시리즈 퍼지 매칭 엔진, 부정 속성 감지기 및 FastAPI 서버 베이스라인 구축

- [ ] T003 [P] Implement series/sub-brand substring and fuzzy expansion helper in `bteam/Oliview_chatbot_a/oliview_core/tools/search_tools.py`
- [ ] T004 [P] Integrate series expansion and negative lexicon recognition into `bteam/Oliview_chatbot_a/oliview_core/utils/entity_normalizer.py`
- [ ] T005 [P] Setup FastAPI application with static file mount and SSE route skeleton in `bteam/Oliview_chatbot_a/main.py`

**Checkpoint**: 시리즈 매칭 도구, 부정 속성 사전, FastAPI 라우팅 베이스 완료 — User Story 개발 진입 가능

---

## Phase 3: User Story 1 - 라인/시리즈명 및 약칭 질의의 실존 상품 자동 매칭 및 리뷰 인용 (Priority: P1) 🎯 MVP

**Goal**: "헤라 센슈얼 립", "차앤박 프로폴리스" 등 시리즈명 질의 시 카탈로그 내 하위 실존 상품 2~3종을 자동 발굴하여 리뷰 수집 및 `[제품명A 리뷰 1]`, `[제품명B 리뷰 1]` 인용과 함께 비교 요약 제공.

**Independent Test**: "헤라 센슈얼 립 촉촉함과 각질부각 분석해줘" 질의 시, "헤라 센슈얼 누드 밤", "헤라 센슈얼 누드 글로스" 등 실존 상품 2종이 매칭되어 실제 리뷰 4건 선별 및 인용 태그 일치 검증.

### Tests for User Story 1 (Test-First TDD) ⚠️
> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T006 [P] [US1] Unit test for series resolution (e.g., "헤라 센슈얼 립" $\rightarrow$ "헤라 센슈얼 누드 밤/글로스" candidates) in `bteam/Oliview_chatbot_a/tests/test_series_resolution.py`
- [ ] T007 [P] [US1] Unit test for multi-target series citation formatting (`[헤라 센슈얼 누드 밤 리뷰 1]`) in `bteam/Oliview_chatbot_a/tests/test_series_citations.py`

### Implementation for User Story 1

- [ ] T008 [US1] Update `router_node.py` to auto-expand series queries into multi-target `EXPLICIT_COMPARE` when $\ge 2$ product candidates match in `bteam/Oliview_chatbot_a/oliview_core/nodes/router_node.py`
- [ ] T009 [US1] Update `search_node.py` to retrieve balanced reviews (max 3 reviews per series product) in `bteam/Oliview_chatbot_a/oliview_core/nodes/search_node.py`
- [ ] T010 [US1] Enforce `[제품명 리뷰 N]` namespace citations and XML context assembly in `bteam/Oliview_chatbot_a/oliview_core/nodes/context_node.py` and `synthesis_node.py`

**Checkpoint**: User Story 1 완성 (시리즈명 약칭 질의 100% 실존 상품 매칭 및 인용 무결성 확보)

---

## Phase 4: User Story 2 - 화장품 도메인 부정 속성어("각질부각", "요철부각", "다크닝") 의미 왜곡 방지 (Priority: P2)

**Goal**: "각질부각", "요철부각", "들뜸", "밀림", "다크닝" 등의 단점 속성이 "각질부각 효과"와 같이 긍정으로 오역되는 현상을 방지하고, 단점/주의점으로 의미 고정 및 0건 리뷰 시 가짜 후기 창작 100% 차단.

**Independent Test**: "각질부각 어때?" 질의 시 아쉬운 점/주의할 점 영역에 올바르게 배치되며, 0건 리뷰 시 `ZERO_SEARCH_TEMPLATE` 확정 렌더링 검증.

### Tests for User Story 2 (Test-First TDD) ⚠️

- [ ] T011 [P] [US2] Unit test for cosmetic negative lexicon guard and polarity constraints in `bteam/Oliview_chatbot_a/tests/test_negative_aspect_guard.py`
- [ ] T012 [P] [US2] Unit test for Zero-Search Hard Block (0 reviews $\rightarrow$ 0 fake pros/cons) in `bteam/Oliview_chatbot_a/tests/test_zero_search_hard_block.py`

### Implementation for User Story 2

- [ ] T013 [US2] Implement negative aspect constraint injector and zero-search hard block in `bteam/Oliview_chatbot_a/oliview_core/nodes/synthesis_node.py`
- [ ] T014 [US2] Implement negative aspect polarity validator and hallucination post-processor in `bteam/Oliview_chatbot_a/oliview_core/guardrail.py`

**Checkpoint**: User Story 1 & 2 완성 (시리즈 발굴 + 뷰티 부정 속성 왜곡 방지 및 제로 서치 무환각 달성)

---

## Phase 5: User Story 3 - ChatA FastAPI 웹 전환 및 Pixel-Identical 데스크탑 UI 계승 (Priority: P3)

**Goal**: ChatA 웹 인터페이스를 FastAPI 백엔드 + 모던 Vanilla Web으로 전환하되, 데스크탑 환경에서 기존 Streamlit ChatA의 시각적 디자인(2열 레이아웃, 컬러 팔레트, 폰트, 상태 박스, 하단 고정 입력창)을 100% 동일하게 재현.

**Independent Test**: 데스크탑 브라우저에서 `http://localhost:8501` 접속 시 기존과 동일한 UI 표시 및 SSE 스트리밍 토큰 수신, 즉시 중단(⏹️) 검증.

### Tests for User Story 3 (Test-First TDD) ⚠️

- [ ] T015 [P] [US3] Integration test for FastAPI SSE stream endpoint (`POST /api/v1/chat/stream`) and token chunks in `bteam/Oliview_chatbot_a/tests/test_fastapi_web_stream.py`

### Implementation for User Story 3

- [ ] T016 [US3] Implement full FastAPI application and SSE event generator in `bteam/Oliview_chatbot_a/main.py`
- [ ] T017 [US3] Build Desktop Pixel-Identical HTML structure (2-column `[1.6:1.4]` brand/category/aspect chips + 1-click examples + bottom fixed bar) in `bteam/Oliview_chatbot_a/static/index.html`
- [ ] T018 [US3] Implement Desktop CSS styling (Pretendard font, Olive Young `#2E9E44`, glassmorphism, status box, review accordion) in `bteam/Oliview_chatbot_a/static/css/style.css`
- [ ] T019 [US3] Implement client-side SSE consumption, real-time status updates, and `AbortController` stop handler in `bteam/Oliview_chatbot_a/static/js/app.js`

**Checkpoint**: User Story 1, 2, 3 완성 (FastAPI 웹 전환 및 데스크탑 Pixel-Identical UI 완성)

---

## Phase 6: User Story 4 - 2026 모바일 최적화 반응형 웹(Responsive Web) 레이아웃 지원 (Priority: P4)

**Goal**: 스마트폰 및 태블릿 접속 시 2026 모바일 UX 트렌드에 최적화된 엄지손가락 중심(Thumb-Zone), 가로 스크롤 칩 필터, 참조 리뷰 바텀 시트(Bottom Sheet) 인터랙션 제공.

**Independent Test**: 모바일 뷰포트(375px~430px) 접속 시 상단 가로 스크롤 칩 바 전환 및 본문 `[리뷰 1]` 탭 시 하단 바텀 시트 슬라이드업 검증.

### Tests for User Story 4 (Test-First TDD) ⚠️

- [ ] T020 [P] [US4] Contract test for mobile viewport responsiveness and bottom sheet event triggers in `bteam/Oliview_chatbot_a/tests/test_mobile_responsive_contract.py`

### Implementation for User Story 4

- [ ] T021 [US4] Implement 2026 Mobile Responsive CSS (`@media (max-width: 768px)`, horizontal swipe chips, Thumb-Zone input bar, safe-area-inset) in `bteam/Oliview_chatbot_a/static/css/mobile.css`
- [ ] T022 [US4] Implement interactive slide-up **Bottom Sheet Drawer** and inline `[리뷰 N]` badge tap handlers in `bteam/Oliview_chatbot_a/static/js/chat_ui.js`

**Checkpoint**: User Story 1~4 전체 기능 완결 (데스크탑 동일 레이아웃 + 2026 모바일 최적화 바텀 시트 반응형 웹 완비)

---

## Phase 7: Polish & Cross-Cutting Integration

**Purpose**: 전사 회귀 검증, ChatB 동기화 및 E2E 실시간 쿼리 품질 검증

- [ ] T023 [P] Execute all new unit and contract test suites with pytest across `bteam/Oliview_chatbot_a/tests/`
- [ ] T024 Synchronize updated core models, tools, and negative aspect guard to `bteam/Oliview_chatbot_b/oliview_core/`
- [ ] T025 Execute end-to-end quickstart validation scenarios from `specs/038-product-series-resolution-and-citation-enforcement/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies
- **Setup (Phase 1)**: No dependencies — starts immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all User Stories.
- **User Story 1 (Phase 3 - MVP)**: Depends on Phase 2.
- **User Story 2 (Phase 4)**: Depends on Phase 2 & 3.
- **User Story 3 (Phase 5)**: Depends on Phase 2, 3, 4.
- **User Story 4 (Phase 6)**: Depends on Phase 5.
- **Polish (Phase 7)**: Depends on Phases 1~6 completion.

### Parallel Opportunities
- T001, T002 (Phase 1) can run in parallel.
- T003, T004, T005 (Phase 2) can run in parallel.
- T006, T007 (US1 Tests) can run in parallel.
- T011, T012 (US2 Tests) can run in parallel.
- T015, T019, T020 (US3/US4 Tests) can run in parallel.
- T023 (Polish Unit Tests) can run in parallel.
