# Tasks: Oliview Chatbot A 대화 입력창 가로 너비 정렬 최적화

**Branch**: `020-align-chata-chatinput-width` | **Date**: 2026-08-19 | **Spec**: [spec.md](file:///c:/AISERVICE/specs/020-align-chata-chatinput-width/spec.md) | **Plan**: [plan.md](file:///c:/AISERVICE/specs/020-align-chata-chatinput-width/plan.md)

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 대상 코드베이스 및 CSS 계약 환경 확인

- [x] T001 [P] Verify Streamlit frontend codebase and custom CSS injection structure in `bteam/Oliview_chatbot_a/app.py`
- [x] T002 [P] Review UI style specifications and invariant contracts in `specs/020-align-chata-chatinput-width/contracts/ui_layout_contract.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 입력창 레이아웃 컨테이너 기본 스타일 기반 마련

- [x] T003 Ensure `.block-container` max-width and horizontal margin standard (1200px, margin auto) in `bteam/Oliview_chatbot_a/app.py`
- [x] T004 Define bottom fixed wrapper positioning and base properties in `bteam/Oliview_chatbot_a/app.py`

**Checkpoint**: Foundation ready - UI layout CSS rules can now be implemented

---

## Phase 3: User Story 1 - 메인 컨텐츠 영역과 일관된 대화 입력창 너비 정렬 (Priority: P1) 🎯 MVP

**Goal**: 와이드 해상도에서 하단 대화 입력창(`st.chat_input`)이 상단 본문 컨테이너(1200px)와 완벽히 일치하여 중앙 정렬되고 반투명 블러 배경이 적용되도록 구현

**Independent Test**: 브라우저 창을 가로 1920px(FHD) 이상으로 열었을 때, 하단 입력창 좌우 시작/끝 지점이 상단 메인 컨텐츠 경계선과 1200px 기준 정확히 일치(0px 오차)하고 스크롤 메시지가 반투명 블러 처리되는지 검증

### Implementation for User Story 1

- [x] T005 [US1] Inject `[data-testid="stBottomBlockContainer"]`, `.stBottomBlockContainer`, and `[data-testid="stChatInput"]` max-width (1200px) and margin auto in `bteam/Oliview_chatbot_a/app.py`
- [x] T006 [US1] Apply glassmorphism backdrop blur (`backdrop-filter: blur(12px)`, `rgba(255, 255, 255, 0.88)`) and border-top on `[data-testid="stBottom"]` in `bteam/Oliview_chatbot_a/app.py`
- [x] T007 [US1] Adjust main content bottom padding to prevent chat messages from being obscured by the bottom bar in `bteam/Oliview_chatbot_a/app.py`

**Checkpoint**: User Story 1 (MVP) is fully functional - chat input width is strictly constrained to 1200px and centered.

---

## Phase 4: User Story 2 - 반응형 화면 크기 변경 시 자동 너비 동기화 (Priority: P2)

**Goal**: 태블릿 및 모바일 기기(360px~1024px)에서 하단 입력창이 본문 컨텐츠와 동일한 비율로 유연하게 축소/확대되고 좌우 패딩을 최적화

**Independent Test**: 브라우저 폭을 1200px 이하(1024px, 768px, 480px, 360px)로 조절했을 때 입력창 잘림이나 가로 스크롤 없이 본문 좌우 여백과 완벽히 동기화되는지 검증

### Implementation for User Story 2

- [x] T008 [US2] Implement responsive media query `@media (max-width: 768px)` with adaptive padding (0.75rem) for bottom input container in `bteam/Oliview_chatbot_a/app.py`
- [x] T009 [US2] Verify input box auto line-wrap and focus states across varying viewport widths in `bteam/Oliview_chatbot_a/app.py`

**Checkpoint**: User Stories 1 AND 2 are both complete and verified.

---

## Phase 5: Polish & Validation

**Purpose**: 최종 시각적 검증 및 퀵스타트 가이드 적합성 확인

- [x] T010 [P] Execute end-to-end visual verification across FHD, QHD, Tablet, and Mobile viewports per `specs/020-align-chata-chatinput-width/quickstart.md`
- [x] T011 [P] Verify 1-click example query buttons, enter-key submission, and session restore compatibility in `bteam/Oliview_chatbot_a/app.py`
- [x] T012 Re-check Spec Quality Checklist and finalize documentation in `specs/020-align-chata-chatinput-width/checklists/requirements.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion
- **User Story 1 (Phase 3)**: Depends on Foundational completion (MVP)
- **User Story 2 (Phase 4)**: Depends on User Story 1 completion
- **Polish (Phase 5)**: Depends on User Stories 1 & 2 completion

### Parallel Opportunities

- T001 and T002 in Setup can be reviewed in parallel
- T010 and T011 in Polish phase can run in parallel

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Setup (T001-T002) + Foundational (T003-T004)
2. Implement User Story 1 (T005-T007)
3. Validate 1200px center alignment and glassmorphism backdrop blur on desktop

### Incremental Delivery
1. Add User Story 2 (T008-T009) for mobile/tablet responsive polish
2. Run Polish & Validation (T010-T012)
