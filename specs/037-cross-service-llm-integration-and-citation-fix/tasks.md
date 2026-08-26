# Tasks: 037-cross-service-llm-integration-and-citation-fix (상호보완형 다중 하이브리드 파이프라인, LangGraph 노드 도구화, 2단계 Top-P 및 ChatA/ChatB 리뷰 인용 무결성 확보)

**Branch**: `037-cross-service-llm-integration-and-citation-fix`  
**Date**: 2026-08-26  
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

---

## Phase 1: Setup (Shared Infrastructure, Tools & Contracts)

**Purpose**: 프로젝트 기초 환경 확인, 데이터 모델, LangGraph 도구 스키마 및 계약 배치

- [X] T001 [P] Create and verify data models and schemas in `bteam/Oliview_chatbot_a/oliview_core/models/citation_models.py`
- [X] T002 [P] Verify Model Gateway 2-Tier serving configuration (`qwen3.5-2b` 64K / `qwen3.5-4b` 32K) in `model_gateway/config/model_catalog.json`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 모든 User Story가 의존하는 하이브리드 캐스케이디드 파서, LangGraph 도구 모듈, 2단계 Top-P 및 환경별(Dev/Prod) 타임아웃 설정 구축

- [X] T003 [P] Implement Hybrid Cascaded Query Parser (Stage 1 Kiwi Fast-Path + Stage 2 Qwen 2B SLM Arbiter Fallback) in `bteam/Oliview_chatbot_a/oliview_core/utils/entity_normalizer.py`
- [X] T004 [P] Implement LangGraph Typed Tools (`tool_search_catalog`, `tool_get_reviews`, `tool_get_specs`) in `bteam/Oliview_chatbot_a/oliview_core/tools/search_tools.py` and `spec_tools.py`
- [X] T005 [P] Implement Document Top-P cumulative mass and score cliff calculator in `bteam/Oliview_chatbot_a/oliview_core/utils/document_top_p.py`
- [X] T006 [P] Configure environment-based lenient timeouts (`sliding_inactivity_timeout_s: 45.0` for Dev mode) and Top-P sampling defaults (`top_p: 0.85`, `temperature: 0.3`, `repetition_penalty: 1.05`) in `bteam/Oliview_chatbot_a/oliview_core/config.py` and `client.py`

**Checkpoint**: 하이브리드 파서, LangGraph 도구, Top-P 유틸리티, 타임아웃 프로파일 구축 완료 — User Story 개발 진입 가능

---

## Phase 3: User Story 1 - ChatA/ChatB 리뷰 인용 출처(Citation) 표기 무결성 및 하이브리드 질의 정규화 (Priority: P1) 🎯 MVP

**Goal**: 서술형 복합 질문 및 속성 충돌 엣지케이스에서 순수 상품명을 분리하여 0건 검색을 방지하고, 본문 내 `[리뷰 1]`, `[리뷰 2]` 인라인 인용 부호 및 UI 아코디언 원문과의 1:1 일치를 보장.

**Independent Test**: "컬러그램 탕후루 탱글 꿀로스의 발림성 장단점을 분석해줘" 및 "닥터자르트 시카페어 진정 크림의 진정 장단점" 질의 시, 상품명 추출, 리뷰 검색 성공, 본문 `[리뷰 N]` 인용 및 UI 아코디언 매칭 검증.

### Tests for User Story 1 (Test-First TDD) ⚠️
> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T007 [P] [US1] Unit test for Hybrid Cascaded Parser (Kiwi Fast-Path + SLM Arbiter) and target normalization in `bteam/Oliview_chatbot_a/tests/test_entity_normalization.py`
- [X] T008 [P] [US1] Unit test for LangGraph Tool execution (`tool_search_catalog`, `tool_get_reviews`) in `bteam/Oliview_chatbot_a/tests/test_langgraph_tools.py`
- [X] T009 [P] [US1] Unit test for inline citation tag parsing, Python post-processor guardrail, and 1:1 UI accordion mapping in `bteam/Oliview_chatbot_a/tests/test_citation_integrity.py`

### Implementation for User Story 1

- [X] T010 [US1] Integrate Hybrid Cascaded Parser into router and search nodes in `bteam/Oliview_chatbot_a/oliview_core/nodes/router_node.py` and `search_node.py`
- [X] T011 [US1] Update XML context assembler with explicit rank tags (`<review rank="N" target="...">`) in `bteam/Oliview_chatbot_a/oliview_core/nodes/context_node.py`
- [X] T012 [US1] Enforce strict `[리뷰 N]` inline citation instructions and Python citation tag normalizer (`[1]` $\rightarrow$ `[리뷰 1]`) in `bteam/Oliview_chatbot_a/oliview_core/nodes/synthesis_node.py`
- [X] T013 [US1] Update Streamlit UI (`app.py`, `06.02.app.py`) and event adapter to render grouped `📚 참조 리뷰 원문` accordion matching `[리뷰 N]` in `bteam/Oliview_chatbot_a/graph_adapter.py`
- [X] T014 [US1] Synchronize entity normalization and citation adapter for ChatB in `bteam/Oliview_chatbot_b/`

**Checkpoint**: User Story 1 완성 및 독립 테스트 통과 (단일 상품 질문 100% 인용 무결성 확보)

---

## Phase 4: User Story 2 - 카테고리/속성 추천(Discovery) 자동 발굴 및 제로 서치 환각 방지 (Priority: P2)

**Goal**: 특정 상품명이 없는 카테고리 추천 질문에 대해 LangGraph 도구로 상위 실존 상품 3~5개를 자동 발굴하여 비교 추천하고, 유효 리뷰 0건 시 가짜 리뷰 창작을 원천 차단하는 제로 서치 가드 구축.

**Independent Test**: (1) "민감성 피부 쿠션팩트 있나요" 질의 시 상위 3종 쿠션팩트 발굴 및 네임스페이스 인용(`[제품명 리뷰 N]`) 추천 검증, (2) 가상 상품 질의 시 0건 부재 안내 검증.

### Tests for User Story 2 (Test-First TDD) ⚠️

- [X] T015 [P] [US2] Test for Category Discovery routing and candidate product retrieval in `bteam/Oliview_chatbot_a/tests/test_category_discovery.py`
- [X] T016 [P] [US2] Test for Zero-Search Hallucination Guard (0 reviews $\rightarrow$ 0 fake quotes) in `bteam/Oliview_chatbot_a/tests/test_zero_search_guard.py`

### Implementation for User Story 2

- [X] T017 [US2] Implement `FEATURE_DISCOVERY` category & attribute keyword mapper using `tool_search_catalog` in `bteam/Oliview_chatbot_a/oliview_core/nodes/router_node.py`
- [X] T018 [US2] Implement multi-target candidate retrieval and review bundling (max 3 reviews per product) in `bteam/Oliview_chatbot_a/oliview_core/nodes/search_node.py`
- [X] T019 [US2] Implement `ZERO_SEARCH_TEMPLATE` with dual branching (spec header vs non-existent apology) in `bteam/Oliview_chatbot_a/oliview_core/nodes/synthesis_node.py`
- [X] T020 [US2] Support multi-target namespace citations (`[제품명A 리뷰 1]`) and multi-turn deep recall (`[Turn N 리뷰 M]`) in `bteam/Oliview_chatbot_a/oliview_core/nodes/synthesis_node.py` and `graph_adapter.py`

**Checkpoint**: User Story 1 & 2 완성 (카테고리 발굴 추천 + 제로 서치 무환각 달성)

---

## Phase 5: User Story 3 - 2단계 Top-P, 실증 데모 피드백/중단/에러 핸들링 및 게이트웨이 연동 표준화 (Priority: P3)

**Goal**: BGE-Reranker 점수 85% 누적 질량 가변 선별(문서 Top-P)과 Qwen 3.5 생성 Top-P(0.85) 적용, 눈속임 없는 실시간 단계 피드백, 사용자 생성 중단(Stop) 기능 및 서버 에러 투명 통지 체계 구축.

**Independent Test**: (1) 문서 Top-P 점수 절벽 컷오프 검증, (2) '생성 중단' 클릭 시 500ms 이내 SSE 종료 및 GPU 자원 해제 검증, (3) 서버 장애 시 투명한 에러 고지 검증, (4) A-Team 뉴스 50건 4B 32K 배치 호출 검증.

### Tests for User Story 3 (Test-First TDD) ⚠️

- [X] T021 [P] [US3] Unit test for Document Top-P selection and Score Cliff early cutoff in `bteam/Oliview_chatbot_a/tests/test_document_top_p.py`
- [X] T022 [P] [US3] Test for real-time pipeline status events, Stop generation cancellation, and transparent error handling in `bteam/Oliview_chatbot_a/tests/test_pipeline_feedback.py`
- [X] T023 [P] [US3] Cross-service integration test for A-Team PILOS Gateway client in `ateam/pilos-sentiment-index/tests/test_pilos_gateway_client.py`

### Implementation for User Story 3

- [X] T024 [US3] Integrate Document Top-P filtering and score cliff cutoff into `bteam/Oliview_chatbot_a/oliview_core/nodes/rerank_node.py`
- [X] T025 [US3] Implement real-time actual pipeline stage emitter, Stop generation handler, and transparent error banner in `bteam/Oliview_chatbot_a/graph_adapter.py`, `app.py`, and `06.02.app.py`
- [X] T026 [US3] Apply `top_p=0.85`, `temperature=0.3`, `repetition_penalty=1.05` across all LLM stream calls in `bteam/Oliview_chatbot_a/oliview_core/client.py` and `bteam/Oliview_chatbot_b/`
- [X] T027 [US3] Standardize A-Team LLM client for Model Gateway 2-Tier routing (`qwen3.5-4b` 32K batch report / `qwen3.5-2b` 64K chat) in `ateam/pilos-sentiment-index/pilos/collection/ai_clients/llm_client.py`

**Checkpoint**: User Story 1, 2, 3 전체 기능 완결 (하이브리드 파서, LangGraph 도구, 2단계 Top-P, 실증 피드백/중단/에러 핸들링 및 전사 게이트웨이 연동 표준화 완비)

---

## Phase 6: Polish & Cross-Cutting Integration

**Purpose**: 전사 7-Suite 통합 회귀 검증, 벤치마크 및 최종 실시간 쿼리 품질 검증

- [X] T028 [P] Execute all new unit and contract test suites with pytest across `bteam/` and `ateam/`
- [X] T029 Execute B-Team 7-Suite Full Regression Runner in `bteam/Oliview_chatbot_b/tests/run_all_regression_tests.py`
- [X] T030 Execute end-to-end quickstart validation scenarios from `specs/037-cross-service-llm-integration-and-citation-fix/quickstart.md`

**Final Checkpoint**: 전사 LLM 연동 일원화, 인용 무결성 복원, 카테고리 발굴, 2단계 Top-P 및 7대 회귀 테스트 100% 검증 완료!

---

## Dependencies & Execution Order

### Phase Dependencies
- **Setup (Phase 1)**: No dependencies — starts immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all User Stories.
- **User Story 1 (Phase 3 - MVP)**: Depends on Phase 2.
- **User Story 2 (Phase 4)**: Depends on Phase 3.
- **User Story 3 (Phase 5)**: Depends on Phase 2 & 4.
- **Polish (Phase 6)**: Depends on Phases 1~5 completion.

### Parallel Opportunities
- T001, T002 (Phase 1) can run in parallel.
- T003, T004, T005, T006 (Phase 2) can run in parallel.
- T007, T008, T009 (US1 Tests) can run in parallel.
- T015, T016 (US2 Tests) can run in parallel.
- T021, T022, T023 (US3 Tests) can run in parallel.
- T028 (Polish Unit Tests) can run in parallel.
