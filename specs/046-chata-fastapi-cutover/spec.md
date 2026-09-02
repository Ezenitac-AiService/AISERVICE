# Feature Specification: Oliview ChatA FastAPI 웹 서비스 완전 전환 및 Uvicorn 단일 엔트리포인트 일원화 (Cutover ChatA to FastAPI Web Service & Uvicorn Single Entrypoint)

**Feature Branch**: `046-chata-fastapi-cutover`

**Created**: 2026-09-02

**Status**: Clarified (Ready for Planning)

**Input**: User inquiry: "아니 chat a가 왜 아직도 streamlit이야? C:\AISERVICE\specs 내역 찾아봐, fastapi로 바꿨을건데, 왜 되돌아가있어?"

---

## Background & History Analysis (배경 및 원인 분석)

1. **Spec 038 (`038-product-series-resolution-and-citation-enforcement`)**:
   - ChatA의 프레임워크를 Streamlit에서 FastAPI + Vanilla Web으로 전환하기 위해 `bteam/Oliview_chatbot_a/main.py` 및 `static/index.html`, `static/css/`, `static/js/app.js`를 개발 완료함.
2. **Spec 040 (`040-chata-mobile-header-and-layout-optimization`) 및 이후 Spec (041, 042, 045)**:
   - Spec 040에서 모바일 CSS 및 3x2 카테고리 그리드 최적화를 진행하면서 신규 FastAPI 웹 대신 기존 `bteam/Oliview_chatbot_a/app.py` (Streamlit) 파일에 수정을 직접 적용함.
   - `bteam/Oliview_chatbot_a/Dockerfile`의 실행 명령(`CMD ["streamlit", "run", "app.py", ...]`)과 전사 배포/실행 가이드가 여전히 Streamlit `app.py`를 가리키고 있어, 실제 기동 환경에서 Streamlit이 계속 실행되는 회귀 현상이 발생함.
3. **본 피처의 목표**:
   - ChatA의 기본 엔트리포인트를 FastAPI(`main.py` on Uvicorn, Port 8501)로 완전히 전환(Cutover)하고, `Dockerfile` 및 서빙 구조를 일원화하며, 레거시 Streamlit `app.py`는 `legacy_archive/`로 격리하여 프레임워크 파편화를 종결함.

---

## Clarifications

### Session 2026-09-02
- Q: FastAPI ChatA 웹 클라이언트의 대화 이력(Chat History)을 백엔드 Redis 세션 저장소(`RedisSessionStore`)와 연동할 것인가요? → A: Option A (Redis 세션 저장소 연동 및 `session_id` 기반 새로고침 세션 복원 지원)
- Q: 프론트엔드 정적 파일 및 API 호출 경로를 상대 경로(`static/...`, `api/v1/...`) 기반으로 구축할 것인가요? → A: Option A (상대 경로 표준화로 로컬 직접 접근과 Nginx 서브패스 동시 완벽 지원)

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 올리뷰 ChatA 메인 웹 서비스의 FastAPI/Uvicorn 완전 전환 및 실시간 SSE 스트리밍 (Priority: P1)

올리뷰 사용자가 웹 브라우저(`http://localhost:8501/` 또는 `https://ezenitac.duckdns.org/bteam/chata/`)로 ChatA에 접속했을 때, 무거운 Streamlit 전체 Re-run 없이 가볍고 빠른 FastAPI 기반 웹 페이지가 즉각 렌더링되며, 질문 입력 시 Server-Sent Events(SSE) 스트리밍을 통해 끊김 없이 실시간 분석 답변과 참조 리뷰를 제공받는다.

**Why this priority**: Streamlit의 Re-run 한계, 프로세스 불안정성 및 `httpx` 모듈 로딩 충돌을 근본적으로 제거하고, 백엔드/프론트엔드가 깔끔히 분리된 프로덕션 급 웹 서비스를 제공하기 위함이다.

**Independent Test**: `uvicorn main:app --port 8501`로 서버를 기동하고 브라우저 접속 및 `/api/v1/chat/stream` 엔드포인트로 질문을 전송하여, HTML 메인 페이지 렌더링과 SSE 토큰 스트리밍이 100% 정상 작동하는지 검증한다.

**Acceptance Scenarios**:

1. **Given** FastAPI ChatA 서버가 8501 포트에서 실행 중일 때, **When** 사용자가 웹 브라우저로 루트 경로(`GET /`)에 접속하면, **Then** Streamlit 로딩 화면 없이 모던 반응형 HTML5 웹 페이지(`static/index.html`)가 즉시 렌더링되어야 한다.
2. **Given** ChatA 웹 페이지에서, **When** 사용자가 "눈시림 없고 순한 선케어 제품 추천해줘"를 입력하면, **Then** 4단계 실시간 상태 표시기(의도 분석 → 검색 → 리랭킹 → 답변 생성)가 갱신되며 부드럽게 토큰이 스트리밍되어야 한다.

---

### User Story 2 - 데스크탑 100% Pixel-Identical 디자인 계승 및 2026 모바일 반응형 UX 지원 (Priority: P1)

기존 Streamlit ChatA에서 호평받았던 시각적 요소(상단 브랜드/카테고리/속성 2열 박스, 1클릭 질문 예시 버튼, 상태 박스, 하단 고정 입력창)가 데스크탑 화면에서 100% 동일하게 재현(Pixel-Identical)되며, 모바일 화면($\le 768\text{px}$)에서는 3x2 카테고리 그리드, Safe-Area 인셋, 참조 리뷰 바텀 시트 드로어가 적용되어 최상의 사용성을 제공한다.

**Why this priority**: 사용자가 프레임워크 변경으로 인한 이질감을 느끼지 않으면서도 모바일 환경에서의 편의성을 극대화하기 위함이다.

**Independent Test**: 데스크탑($\ge 768\text{px}$) 및 모바일($\le 768\text{px}$) 뷰포트에서 각각 카테고리 칩 클릭, 질문 예시 1클릭 실행, 참조 리뷰 아코디언 토글 인터랙션이 올바르게 동작하는지 검증한다.

**Acceptance Scenarios**:

1. **Given** 데스크탑 브라우저 환경에서, **When** ChatA 페이지를 열면, **Then** 좌측 브랜드/카테고리/속성 박스와 우측 질문 예시 패널이 2열로 정렬되어 기존 ChatA 레이아웃과 100% 일치해야 한다.
2. **Given** 모바일 브라우저 환경에서, **When** 상단 카테고리 버튼을 누르면, **Then** 3열 2행의 컴팩트 그리드로 표시되고 해당 카테고리에 맞는 분석 속성 칩과 1클릭 질문 예시가 즉시 동적 갱신되어야 한다.

---

### User Story 3 - Dockerfile, 배포 환경설정 및 런타임 엔트리포인트 일원화 (Priority: P2)

컨테이너 빌드 및 배포 인프라(`Dockerfile`, 배포 스크립트)가 Streamlit 대신 Uvicorn 기반 FastAPI 실행 명령으로 일원화되며, 불필요한 Streamlit 레거시 스크립트(`app.py`)는 `legacy_archive/`로 안전하게 격리 보관된다.

**Why this priority**: 배포 환경과 로컬 환경 간의 실행 엔트리포인트 불일치를 완전히 제거하고, Docker 컨테이너 재빌드 시 항상 FastAPI 서비스가 기동되도록 보장하기 위함이다.

**Independent Test**: Docker 컨테이너를 빌드/실행했을 때 Uvicorn 프로세스가 포트 8501에서 정상 기동되고 Streamlit 프로세스가 실행되지 않는지 검증한다.

**Acceptance Scenarios**:

1. **Given** `bteam/Oliview_chatbot_a/Dockerfile`이 빌드될 때, **When** 컨테이너가 실행되면, **Then** `uvicorn main:app --host 0.0.0.0 --port 8501` 명령으로 구동되어 정상 헬스체크(`GET /health` -> 200 OK)가 반환되어야 한다.
2. **Given** 소스코드 디렉토리에서, **When** 레거시 정리가 완료되면, **Then** `bteam/Oliview_chatbot_a/app.py`는 `legacy_archive/`로 이동되고 프로젝트 루트에는 `main.py`가 단일 메인 엔트리포인트로 존재해야 한다.

---

## Edge Cases

- **네트워크 단절 또는 LLM 응답 지연**: SSE 스트리밍 중 타임아웃 발생 시 UI에 명확하고 친절한 에러 배너가 출력되고 재시도 버튼이 노출되어야 한다.
- **0건 부재 고지(Zero-Search)**: 데이터가 없는 질문 입력 시 LLM 호출 없이 0초대에 정직한 부재 고지와 추천 카테고리 칩이 즉시 렌더링되어야 한다.
- **모바일 Safe-Area 인셋**: 노치(Notch) 및 하단 홈 바가 있는 최신 스마트폰에서 헤더 및 하단 입력바가 잘리지 않아야 한다.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 시스템은 `bteam/Oliview_chatbot_a`의 기본 웹 서빙 엔진을 Uvicorn 기반 FastAPI(`main.py`, Port 8501)로 확정하고 이를 전역 단일 진실 공급원(SSOT)으로 삼아야 한다.
- **FR-002**: 시스템은 `static/index.html`, `static/css/`, `static/js/app.js`를 통해 데스크탑($\ge 768\text{px}$) 2열 레이아웃 및 모바일($\le 768\text{px}$) 3x2 카테고리 그리드, Safe-Area 인셋, 1클릭 질문 예시를 완벽히 렌더링해야 한다.
- **FR-003**: 시스템은 `POST /api/v1/chat/stream` 엔드포인트를 통해 `MultiTargetGraphOrchestrator`와 실시간 SSE 스트리밍 통신을 수행하고 실시간 4단계 상태 표시기 이벤트를 전송해야 한다.
- **FR-004**: 시스템은 `bteam/Oliview_chatbot_a/Dockerfile`의 진입점(`CMD`)을 `uvicorn main:app --host 0.0.0.0 --port 8501`로 갱신하여 컨테이너 환경에서 FastAPI가 구동되도록 해야 한다.
- **FR-005**: 시스템은 기존 Streamlit 전용 스크립트(`app.py`)를 `bteam/Oliview_chatbot_a/legacy_archive/`로 안전하게 격리 이전하여 코드베이스의 단일 엔트리포인트를 보장해야 한다.
- **FR-006**: 시스템은 `session_id` 기반으로 Redis 세션 저장소(`RedisSessionStore`)와 연동하여 대화 이력을 보존하고, 세션 이력 조회 엔드포인트(`GET /api/v1/chat/history/{session_id}`)를 통해 새로고침 시에도 이전 대화 내역이 복원되도록 해야 한다.
- **FR-007**: 시스템은 `static/index.html` 및 `static/js/app.js` 내의 모든 정적 자산 및 SSE API 엔드포인트 URL을 상대 경로(`static/...`, `api/v1/...`)로 구성하여, 로컬 루트(`http://localhost:8501/`)와 Nginx 리버스 프록시 서브패스(`https://ezenitac.duckdns.org/bteam/chata/`) 환경 모두에서 404 리소스 누락 없이 즉시 구동되도록 해야 한다.

---

## Key Entities

- **ChatStreamRequest**: 사용자 질의문(`query`), 세션 식별자(`session_id`), 카테고리 힌트(`category_hint`)를 담은 Pydantic 요청 스키마.
- **ChatStreamEvent**: 실시간 단계 상태(`step_update`), 텍스트 청크(`token_chunk`), 최종 완료 메타데이터(`final_result`), 에러(`error`)를 표현하는 표준 SSE 이벤트.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `GET http://localhost:8501/` 접속 시 100% 정상적인 HTML5 웹 메인 화면이 0.5초 이내에 렌더링된다.
- **SC-002**: 대표 질의("눈시림 없고 순한 선케어 제품 추천해줘") 실행 시 0건 부재 고지 없이 정상 분석 답변이 실시간 SSE 스트리밍으로 출력된다.
- **SC-003**: 뷰포트 $768\text{px}$ 이하 모바일 환경에서 상단 헤더 잘림 0건 및 3x2 카테고리 버튼 터치 정상 작동 100%.
- **SC-004**: `bteam/Oliview_chatbot_a/Dockerfile` 빌드 및 실행 시 Uvicorn 프로세스 정상 구동 (HTTP 200) 및 Streamlit 프로세스 잔재 0건.
- **SC-005**: ChatA 관련 단위 및 통합 테스트(`test_fastapi_web_stream.py`, `test_bteam_rag_recovery.py`) 100% 통과.

---

## Assumptions

- **포트 할당**: 기존 Streamlit이 사용하던 8501 포트를 그대로 FastAPI 메인 서비스 포트로 승계하여 Nginx 리버스 프록시 설정과의 하위 호환성을 유지한다.
- **백엔드 RAG 엔진**: `MultiTargetGraphOrchestrator` 및 `bteam/oliview_core`의 통합 파이프라인을 그대로 활용한다.
- **브라우저 지원**: Chrome, Safari, Edge, 모바일 WebKit 등 모던 브라우저 환경을 지원한다.
