# Tasks: Oliview ChatA FastAPI 웹 서비스 완전 전환 및 Uvicorn 단일 엔트리포인트 일원화 (046-chata-fastapi-cutover)

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Branch**: `046-chata-fastapi-cutover`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 프로젝트 환경 확인 및 기반 디렉토리/테스트 설정

- [X] T001 Verify FastAPI dependencies (`fastapi`, `uvicorn`, `sse-starlette`, `httpx`, `pydantic`) in `bteam/Oliview_chatbot_a/pyproject.toml` and `bteam/pyproject.toml`
- [X] T002 [P] Setup legacy quarantine folder `bteam/Oliview_chatbot_a/legacy_archive/` per Constitution III
- [X] T003 [P] Configure pytest test runner settings and pythonpath in `bteam/Oliview_chatbot_a/pyproject.toml`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 모든 User Story 구현에 공통으로 필요한 데이터 스키마 및 세션 조회 인터페이스

**⚠️ CRITICAL**: 이 단계가 완료되어야 User Story 1~3 구현이 병렬/순차적으로 진행될 수 있습니다.

- [X] T004 [P] Define `ChatStreamRequest`, `ChatStreamEvent`, `SessionHistoryResponse` Pydantic models in `bteam/Oliview_chatbot_a/oliview_core/models/series_models.py`
- [X] T005 [P] Implement Redis session history retrieval and formatting helper in `bteam/Oliview_chatbot_a/oliview_core/session.py`
- [X] T006 [P] Verify `MultiTargetGraphOrchestrator` SSE streaming event schema alignment in `bteam/Oliview_chatbot_a/oliview_core/graph_orchestrator.py`

**Checkpoint**: 공통 데이터 모델 및 세션 저장소 기반 완료 — User Story 구현 진입 가능

---

## Phase 3: User Story 1 - 올리뷰 ChatA 메인 웹 서비스의 FastAPI/Uvicorn 완전 전환 및 실시간 SSE 스트리밍 (Priority: P1) 🎯 MVP

**Goal**: ChatA 웹 애플리케이션의 메인 진입점을 FastAPI `main.py`로 구축하고 SSE 스트리밍 및 Redis 세션 복원 엔드포인트를 제공하여 무거운 Streamlit 의존성을 제거한다.

**Independent Test**: `uvicorn main:app --port 8501` 실행 후 `GET /`, `GET /health`, `POST /api/v1/chat/stream`, `GET /api/v1/chat/history/{session_id}` 엔드포인트가 정상 작동하는지 자동화 테스트로 검증.

### Tests for User Story 1 ⚠️

- [X] T007 [P] [US1] Unit and integration test for FastAPI endpoints (`/`, `/health`, `/api/v1/chat/stream`, `/api/v1/chat/history/{session_id}`) in `bteam/Oliview_chatbot_a/tests/test_fastapi_web_stream.py`

### Implementation for User Story 1

- [X] T008 [US1] Implement FastAPI application structure, CORS, and static file mount in `bteam/Oliview_chatbot_a/main.py`
- [X] T009 [US1] Implement real-time SSE generator (`sse_event_generator`) and `/api/v1/chat/stream` route in `bteam/Oliview_chatbot_a/main.py`
- [X] T010 [US1] Implement `/api/v1/chat/history/{session_id}` route to restore previous messages from `RedisSessionStore` in `bteam/Oliview_chatbot_a/main.py`
- [X] T011 [US1] Add exception handling, timeout safeguards, and trace_id propagation in `bteam/Oliview_chatbot_a/main.py`

**Checkpoint**: User Story 1 완료 (FastAPI 백엔드 및 SSE 스트리밍 엔드포인트 완전 가동)

---

## Phase 4: User Story 2 - 데스크탑 100% Pixel-Identical 디자인 계승 및 2026 모바일 반응형 UX 지원 (Priority: P1)

**Goal**: Vanilla HTML5/CSS3/ES6 기반 프론트엔드를 구축하여 데스크탑에서는 기존 Streamlit 2열 디자인을 100% 동일하게 재현하고, 모바일에서는 3x2 카테고리 그리드와 바텀 시트 인용 드로어를 제공한다.

**Independent Test**: 브라우저에서 `http://localhost:8501/` 접속 시 데스크탑 2열 레이아웃, 모바일 3x2 카테고리 그리드, 1클릭 질문 예시 바인딩, SSE 실시간 토큰 렌더링 검증.

### Implementation for User Story 2

- [X] T012 [P] [US2] Implement desktop 2-column layout, header, brand/category panels, and fixed bottom chat input in `bteam/Oliview_chatbot_a/static/index.html`
- [X] T013 [P] [US2] Implement CSS styling for desktop 2-column layout, 4-stage status indicator, and mobile 3x2 category grid (`@media (max-width: 768px)`) with Safe-Area insets in `bteam/Oliview_chatbot_a/static/css/style.css`
- [X] T014 [US2] Implement SSE streaming reader, auto-scroll, 4-stage status updater, 1-click example query dispatcher, and citation accordion toggle in `bteam/Oliview_chatbot_a/static/js/app.js`
- [X] T015 [US2] Implement relative path standardizations (`static/...`, `api/v1/...`) and sessionStorage `session_id` history restoration in `bteam/Oliview_chatbot_a/static/js/app.js`

**Checkpoint**: User Story 2 완료 (데스크탑/모바일 반응형 웹 UI 및 실시간 스트리밍 연동 완료)

---

## Phase 5: User Story 3 - Dockerfile, 배포 환경설정 및 런타임 엔트리포인트 일원화 (Priority: P2)

**Goal**: `Dockerfile` 실행 명령을 Uvicorn 기반 FastAPI로 교체하고 기존 Streamlit `app.py`를 `legacy_archive/`로 격리하여 런타임 단일 진실 공급원(SSOT)을 확립한다.

**Independent Test**: `Dockerfile` 빌드 및 컨테이너 기동 시 Uvicorn 프로세스가 포트 8501에서 정상 기동되고 Streamlit 프로세스가 실행되지 않는지 검증.

### Implementation for User Story 3

- [X] T016 [US3] Update `bteam/Oliview_chatbot_a/Dockerfile` `CMD` to `["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8501"]`
- [X] T017 [US3] Move and quarantine `bteam/Oliview_chatbot_a/app.py` to `bteam/Oliview_chatbot_a/legacy_archive/06.03.app.py`
- [X] T018 [US3] Synchronize `bteam/oliview_core` with `bteam/Oliview_chatbot_a/oliview_core` and `bteam/Oliview_chatbot_b/oliview_core` per Constitution III

**Checkpoint**: User Story 3 완료 (배포 인프라 및 단일 엔트리포인트 전환 완료)

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 전사 테스트 스위트 전수 실행 및 최종 검증

- [X] T019 [P] Execute full test suite `pytest bteam/Oliview_chatbot_a/tests/test_fastapi_web_stream.py` and `pytest bteam/Oliview_chatbot_a/tests/test_bteam_rag_recovery.py`
- [X] T020 Run end-to-end verification scenario in `specs/046-chata-fastapi-cutover/quickstart.md` and confirm 0ms zero-search and live SSE streaming


---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 즉시 시작 가능
- **Foundational (Phase 2)**: Phase 1 완료 후 시작 — User Story 1, 2, 3를 블로킹
- **User Story 1 (Phase 3)**: Phase 2 완료 후 시작 (백엔드 코어 & SSE 엔드포인트)
- **User Story 2 (Phase 4)**: Phase 2 완료 후 시작 (프론트엔드 UI & SSE 클라이언트 연동) — US1과 병렬 또는 직렬 진행 가능
- **User Story 3 (Phase 5)**: Phase 3, 4 완료 후 진행 (Dockerfile 갱신 및 `app.py` 레거시 격리)
- **Polish (Phase 6)**: 모든 User Story 완료 후 전수 회귀 검증

### Parallel Opportunities

- Phase 1: `T002`, `T003` 병렬 진행 가능
- Phase 2: `T004`, `T005`, `T006` 병렬 진행 가능
- Phase 3 & 4: `T007`(테스트 작성)과 `T012`, `T013`(HTML/CSS 마크업) 병렬 진행 가능
- Phase 6: `T019` 테스트 자동 실행

---

## Implementation Strategy (MVP First)

1. **Phase 1 & 2 완료**: 공통 데이터 스키마 및 세션 헬퍼 정비
2. **Phase 3 (User Story 1 - MVP)**: FastAPI 백엔드 엔드포인트 및 SSE 스트림 완성 → 단위 테스트 통과
3. **Phase 4 (User Story 2)**: HTML/CSS/JS 데스크탑 2열 + 모바일 3x2 반응형 UI 완성 → 브라우저 스트리밍 연동
4. **Phase 5 (User Story 3)**: Dockerfile `CMD` 갱신 및 Streamlit `app.py` 격리 → SSOT 단일화
5. **Phase 6**: 전수 테스트 스위트 패스 및 프로덕션 컷오버 검증
