# Tasks: OllyChat RAG 파이프라인 실시간 시각적 진행과정

**Feature**: `014-ollychat-process-visualization`  
**Date**: 2026-08-19  
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)  

---

## Phase 1: Setup & Shared Infrastructure

**Purpose**: 프로젝트 공통 StepCallbackProtocol 및 이벤트 데이터 모델 초기화

- [x] T001 Create StepCallbackProtocol and PipelineStepEvent models in bteam/Oliview_chatbot_a/common/step_callback.py
- [x] T002 [P] Update common step event definitions and helper types in bteam/Oliview_chatbot_b/common.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: RAG 엔진 코어의 수명 주기 이벤트 디스패치 및 SSE 스트리밍 기반 구축 (모든 User Story의 필수 선행 단계)

**⚠️ CRITICAL**: 이 단계가 완료되어야 User Story 구현을 시작할 수 있습니다.

- [x] T003 [P] Create contract and unit tests for StepCallbackProtocol in tests/test_step_callback_a.py
- [x] T004 [P] Create contract and unit tests for SSE stream endpoint in tests/test_sse_stream_b.py
- [x] T005 Implement StepCallbackProtocol integration and phase lifecycle triggers in bteam/Oliview_chatbot_a/05.chatbot.py
- [x] T006 Implement /api/v1/search/stream SSE endpoint and step event broadcaster in bteam/Oliview_chatbot_b/project_ragapi.py

**Checkpoint**: 콜백 및 SSE 통신 기반 완성 - 이후 User Story 구현 및 병렬 진행 가능

---

## Phase 3: User Story 1 - 실시간 4단계 파이프라인 진행 시각화 및 토큰 스트리밍 (Priority: P1) 🎯 MVP

**Goal**: 질문 전송 시 4단계(의도 분석 ➡️ 검색 ➡️ 리랭킹 ➡️ LLM 생성) 실시간 상태를 시각적으로 노출하고, 토큰 단위 스트리밍 출력 및 완료 시 요약 뱃지로 자동 축약합니다.

**Independent Test**:
- 올리챗 A(`06.app.py`): 질문 입력 시 `st.status`가 4단계 로그를 순차 출력하고, `st.write_stream`으로 답변이 실시간 타이핑된 후 `✅ 분석 완료` 뱃지로 자동 축약되는지 확인.
- 올리챗 B(`index.html`): 웹 화면에서 SSE를 통해 4단계 타임라인 뱃지가 순차 활성화되고 타이핑 애니메이션 후 축약되는지 확인.

### Tests for User Story 1
- [x] T007 [P] [US1] Create unit tests for Streamlit st.status state transitions and token generator in tests/test_ui_streamlit_flow.py
- [x] T008 [P] [US1] Create unit tests for Web UI SSE event listener and typewriter rendering in tests/test_web_sse_client.py

### Implementation for User Story 1
- [x] T009 [US1] Implement real-time 4-step st.status container and st.write_stream token output in bteam/Oliview_chatbot_a/06.app.py
- [x] T010 [US1] Implement chat history rendering with collapsed summary badge for past turns in bteam/Oliview_chatbot_a/06.app.py
- [x] T011 [US1] Implement 4-step progress timeline container and SSE client consumer in bteam/Oliview_chatbot_b/index.html
- [x] T012 [US1] Implement automatic collapse to summary badge with click-to-expand toggle in bteam/Oliview_chatbot_b/index.html

**Checkpoint**: User Story 1(MVP) 완성 - 실시간 4단계 시각화 및 스트리밍이 올리챗 A/B에서 독립적으로 완전 동작함.

---

## Phase 4: User Story 2 - 검색 근거 및 처리 메타데이터 열람 (Priority: P2)

**Goal**: 답변 하단에 실제 AI 답변 근거로 활용된 상위 올리브영 구매자 리뷰 원문(3~5건) 아코디언과 처리 메타데이터(소요시간, 참조건수, 모델명)를 노출합니다.

**Independent Test**:
- 답변 하단의 `📖 실제 참조 리뷰 원문 (N건)` 아코디언을 클릭하여 평점, 피부타입/속성, 리뷰 원문이 올바르게 렌더링되는지 확인.

### Tests for User Story 2
- [x] T013 [P] [US2] Create unit tests for reference review extraction and ranking structure in tests/test_reference_reviews.py

### Implementation for User Story 2
- [x] T014 [US2] Implement reference review accordion and metadata badges in bteam/Oliview_chatbot_a/06.app.py
- [x] T015 [US2] Implement reference review accordion and metadata summary cards in bteam/Oliview_chatbot_b/index.html

**Checkpoint**: User Story 1과 2가 결합되어 실시간 진행 표시 및 근거 리뷰 열람이 완벽히 동작함.

---

## Phase 5: User Story 3 - 예외, 0건 검색 및 폴백 복구 인터랙션 (Priority: P2)

**Goal**: 모델 지연 시 2B 폴백 상태 안내를 제공하고, 검색 결과 0건 또는 장애 발생 시 '다시 시도(Retry)' 버튼 및 '추천 검색어 칩(Chip)'을 통해 1클릭 복구를 지원합니다.

**Independent Test**:
- 등록되지 않은 더미 브랜드 검색 시 상태 박스가 경고로 전환되고 `다시 시도` 및 `추천 검색어 칩`이 나타나며, 칩 클릭 시 즉시 재검색이 수행되는지 확인.

### Tests for User Story 3
- [x] T016 [P] [US3] Create unit tests for 0-result detection and fallback recommendation generation in tests/test_fallback_recovery.py

### Implementation for User Story 3
- [x] T017 [US3] Implement 2B fallback real-time status message in bteam/Oliview_chatbot_a/05.chatbot.py and bteam/Oliview_chatbot_a/06.app.py
- [x] T018 [US3] Implement retry button and recommendation chips on 0-match or error in bteam/Oliview_chatbot_a/06.app.py
- [x] T019 [US3] Implement retry button and recommendation chips on 0-match or error in bteam/Oliview_chatbot_b/index.html

**Checkpoint**: 모든 예외 상황 및 복구 경로가 안정적으로 지원됨.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 전반적인 성능, 호환성, 문서화 및 퀵스타트 전체 시나리오 검증

- [x] T020 [P] Update inline code documentation and comments in bteam/Oliview_chatbot_a/06.app.py and bteam/Oliview_chatbot_b/project_ragapi.py
- [x] T021 Validate UI rendering latency overhead (<50ms) per SC-001 and FR-008 in tests/test_performance_overhead.py
- [x] T022 Execute end-to-end verification scenarios per specs/014-ollychat-process-visualization/quickstart.md

---

## Dependencies & Execution Order

### Phase Dependencies
- **Phase 1 (Setup)**: 의존성 없음 - 즉시 시작 가능.
- **Phase 2 (Foundational)**: Phase 1 완료 필요 - **모든 User Story의 필수 블로커**.
- **Phase 3 (User Story 1 - MVP)**: Phase 2 완료 후 즉시 시작.
- **Phase 4 (User Story 2)**: Phase 2 완료 후 시작 (US1과 병렬 또는 순차 진행 가능).
- **Phase 5 (User Story 3)**: Phase 2 완료 후 시작 (US1/US2와 병렬 또는 순차 진행 가능).
- **Phase 6 (Polish)**: 모든 User Story(Phase 3~5) 완료 후 최종 실행.

### User Story Dependencies
- **US1 (P1)**: Foundational 완료 후 독립 실행 가능 (MVP).
- **US2 (P2)**: Foundational 완료 후 독립 실행 가능 (US1 UI 컨테이너에 아코디언 추가).
- **US3 (P2)**: Foundational 완료 후 독립 실행 가능 (US1/US2 상태 박스에 복구 칩 추가).

---

## Parallel Opportunities

- **Phase 1**: `T001`(올리챗 A)과 `T002`(올리챗 B)는 서로 다른 서브프로젝트이므로 완전 병렬 실행 가능.
- **Phase 2**: `T003`(올리챗 A 테스트)과 `T004`(올리챗 B 테스트) 병렬 작성 가능.
- **Phase 3 (US1)**: `T007`(A 테스트)과 `T008`(B 테스트) 병렬 실행 가능. `T009/T010`(A Streamlit)과 `T011/T012`(B Web UI) 병렬 구현 가능.
- **Phase 4 (US2)**: `T014`(A 아코디언)와 `T015`(B 아코디언) 병렬 구현 가능.
- **Phase 5 (US3)**: `T018`(A 복구 칩)과 `T019`(B 복구 칩) 병렬 구현 가능.

---

## Parallel Example: User Story 1

```bash
# 올리챗 A와 올리챗 B의 테스트를 동시에 작성:
Task: "Create unit tests for Streamlit st.status state transitions in tests/test_ui_streamlit_flow.py"
Task: "Create unit tests for Web UI SSE event listener in tests/test_web_sse_client.py"

# 올리챗 A와 올리챗 B의 UI 구현을 독립적으로 동시 진행:
Task: "Implement real-time 4-step st.status container in bteam/Oliview_chatbot_a/06.app.py"
Task: "Implement 4-step progress timeline container in bteam/Oliview_chatbot_b/index.html"
```

---

## Implementation Strategy

### 1. MVP First (User Story 1)
1. Phase 1(Setup) ➡️ Phase 2(Foundational) 완료.
2. Phase 3(User Story 1: 4단계 실시간 시각화 + 스트리밍 + 자동 축약) 완료.
3. **STOP & VALIDATE**: 올리챗 A 및 B에서 실시간 진행 인디케이터가 정상 동작하는지 독립 검증 (MVP 달성).

### 2. Incremental Delivery
1. Foundation + US1 ➡️ 핵심 실시간 4단계 UX 제공 (MVP).
2. + US2 ➡️ 상위 참조 리뷰 원문 아코디언 열람 기능 확장.
3. + US3 ➡️ 0건/에러 시 복구 칩 및 2B 폴백 안전성 확보.
4. Phase 6 Polish ➡️ 성능 검증 및 퀵스타트 E2E 확인.
