# Tasks: E2E 서비스 안정화 및 서브서비스 종합 점검 (003-e2e-service-stabilization)

**Feature**: `003-e2e-service-stabilization`  
**Spec**: [spec.md](file:///c:/AISERVICE/specs/003-e2e-service-stabilization/spec.md) | **Plan**: [plan.md](file:///c:/AISERVICE/specs/003-e2e-service-stabilization/plan.md)

---

## Phase 1: Setup (공통 인프라 및 환경 설정)

**Purpose**: 서비스 환경 변수 및 공통 스크립트 기반 구조 준비

- [X] T001 루트 `.env` 및 `.env.example`에 Gmail SMTP 설정 (`SMTP_SERVER`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`) 표준화 및 누락 확인 in `.env`, `.env.example`
- [X] T002 [P] `docker-compose.yml`의 `oliview_backend` 서비스에 SMTP 환경 변수 전달 블록 추가 in `docker-compose.yml`
- [X] T003 [P] E2E 자동화 검증 스크립트 디렉토리 생성 in `specs/003-e2e-service-stabilization/scripts/`

---

## Phase 2: Foundational (게이트웨이 라우팅 및 공통 인프라 선행 정비)

**Purpose**: 모든 사용자 스토리가 통과해야 하는 Nginx 게이트웨이 역방향 프록시 라우팅 토폴로지 완비

- [X] T004 `gateway/nginx.conf`에 Pilos 종목 상세(`/stocks/`) 및 어바웃(`/about`) 프록시 라우팅 블록 추가 in `gateway/nginx.conf`
- [X] T005 [P] `gateway/nginx.conf`의 Oliview API(`/bteam/oliview/api/`), 올리챗(`/bteam/chata/`), 올원챗(`/bteam/chatb/`) 프록시 버퍼링 및 타임아웃 정합성 검증 in `gateway/nginx.conf`

**Checkpoint**: 게이트웨이 라우팅 기반 완비 — 서브시스템별 독립 구현 및 테스트 진행 가능

---

## Phase 3: User Story 1 - Pilos 종목 상세 페이지 및 챗봇 리포트 조회 (Priority: P1) 🎯 MVP

**Goal**: Pilos 메인 대시보드에서 종목 카드 클릭 시 404 없이 상세 화면(`/stocks/005930`)으로 정상 이동하고, 일별 감성 지표 및 LLM 리포트가 정상 출력되도록 보장

**Independent Test**: 브라우저에서 `https://ezenitac.duckdns.org/ateam/pilos/` 접속 후 삼성전자(`005930`) 카드 클릭 시 `/stocks/005930` 또는 `/ateam/pilos/stocks/005930` 페이지가 200 OK로 로드되고 리포트 챗봇 조회가 정상 작동하는지 확인

- [X] T006 [P] [US1] Pilos 프론트엔드 `index.js`에 서브경로(`/ateam/pilos`) 자동 감지 동적 베이스 경로 헬퍼 및 종목 링크 생성 적용 in `ateam/pilos-sentiment-index/pilos/web/static/js/index.js`
- [X] T007 [P] [US1] Pilos 프론트엔드 `detail.js` 및 `chat.js`의 API 호출 경로 동기화 및 404 방지 in `ateam/pilos-sentiment-index/pilos/web/static/js/detail.js`, `ateam/pilos-sentiment-index/pilos/web/static/js/chat.js`
- [X] T008 [US1] Pilos 웹 백엔드(`app.py`)의 `/stocks/<stock_code>`, `/about`, `/api/stocks/<stock_code>/llm-reports` 엔드포인트 응답 및 DB 연결 검증 in `ateam/pilos-sentiment-index/pilos/web/app.py`

**Checkpoint**: User Story 1 (Pilos 종목 상세 네비게이션 및 리포트) 독립 검증 완료

---

## Phase 4: User Story 2 - Oliview 로그인 및 브랜드 고유 번호 조회 (Priority: P1)

**Goal**: Oliview 메인 및 로그인 화면에서 3,062개 브랜드 조회 및 검색이 정상 작동하고, 회원가입 시 SMTP 이메일 인증이 안전하게 발송되도록 보장

**Independent Test**: `https://ezenitac.duckdns.org/bteam/oliview/login` 접속 후 브랜드 검색 시 3,062개 브랜드 목록이 검색되고 선택되는지 확인하며, `POST /bteam/oliview/api/send-auth-code` 호출 시 200 OK 또는 정형화된 400 에러를 반환하는지 확인

- [X] T009 [P] [US2] Oliview 백엔드 `app.py`에 `GET /api/brands` 엔드포인트(전체 3,062개 브랜드 조회 및 keyword 필터링) 신설 in `bteam/Oliview_Project/backend/app.py`
- [X] T010 [P] [US2] Oliview 백엔드 `app.py`의 `GET /api/search-brands`를 `GET /api/brands` 별칭으로 연결 및 하위 호환성 보장 in `bteam/Oliview_Project/backend/app.py`
- [X] T011 [US2] Oliview 백엔드 `app.py`의 `POST /api/send-auth-code`에 SMTP 예외 발생 시 `400 Bad Request` 에러 응답 및 인증코드 TTL(5분)/시도 제한(5회) 적용 in `bteam/Oliview_Project/backend/app.py`
- [X] T012 [US2] Oliview 프론트엔드 `LoginPage.jsx` 및 `RegisterPage.jsx`의 브랜드 검색 모달과 이메일 인증 발송 연동 검증 in `bteam/Oliview_Project/frontend/src/LoginPage.jsx`, `bteam/Oliview_Project/frontend/src/RegisterPage.jsx`

**Checkpoint**: User Story 2 (Oliview 브랜드 조회 및 SMTP 인증) 독립 검증 완료

---

## Phase 5: User Story 3 - 올리챗 (ChatA) LLM & HTTP 임베딩 완전 연동 (Priority: P1)

**Goal**: 올리챗 Streamlit 컨테이너에서 로컬 모델 파일 시스템 경로 의존성을 전면 제거하고, 공통 모델 게이트웨이(8090) HTTP BGE-M3 임베딩 및 LLM(8081) 연동을 완결

**Independent Test**: `https://ezenitac.duckdns.org/bteam/chata/` 접속 후 "컬러그램 탕후루 탱글 꿀로스의 발림성 장단점을 분석해줘" 질의 시 `FileNotFoundError` 없이 하이브리드 RAG 및 LLM 분석 답변이 정상 생성되는지 확인

- [X] T013 [P] [US3] 올리챗 `06.02.app.py` 및 `05.chatbot.py`에서 로컬 BGE-M3 가중치 파일 탐색을 제거하고 `HttpBgeM3Embeddings` (8090) 호출로 단일화 in `bteam/Oliview_chatbot_a/06.02.app.py`, `bteam/Oliview_chatbot_a/05.chatbot.py`
- [X] T014 [P] [US3] 올리챗 `03.hybrid_search.py` 및 `02.search_chroma.py`의 로컬 모델 로딩 분기 정리 및 원격 임베딩 클라이언트 적용 in `bteam/Oliview_chatbot_a/03.hybrid_search.py`, `bteam/Oliview_chatbot_a/02.search_chroma.py`
- [X] T015 [US3] 올리챗 RAG 검색 결과 부재 시 환각 생성을 방지하는 표준 폴백 안내문 적용 in `bteam/Oliview_chatbot_a/06.02.app.py`

**Checkpoint**: User Story 3 (올리챗 BGE-M3 HTTP 임베딩 및 LLM) 독립 검증 완료

---

## Phase 6: User Story 4 - 올원챗 (ChatB) 단독 웹 인터페이스 서빙 및 라우팅 (Priority: P2)

**Goal**: 올원챗 FastAPI 웹 인터페이스(`https://ezenitac.duckdns.org/bteam/chatb/`)가 404 없이 즉시 렌더링되고, 하이브리드 RAG 검색 및 Qwen LLM 종합 답변이 정상 작동하도록 보장

**Independent Test**: `https://ezenitac.duckdns.org/bteam/chatb/` 접속 후 올원챗 웹 UI 로딩 및 검색창에 "건성 피부 보습 앰플" 입력 시 추천 상품 목록과 AI 요약이 렌더링되는지 확인

- [X] T016 [P] [US4] 올원챗 `project_ragapi.py`의 FastAPI `root_path="/bteam/chatb"` 및 정적 파일 마운트(`/index.html`) 경로 정렬 in `bteam/Oliview_chatbot_b/project_ragapi.py`
- [X] T017 [P] [US4] 올원챗 `index.html` 내 자바스크립트의 RAG 검색 API 호출 경로를 서브경로(`/bteam/chatb/api/v1/search`) 및 상대 경로로 동기화 in `bteam/Oliview_chatbot_b/index.html`
- [X] T018 [US4] 올원챗 `project_ragapi.py`의 RAG 검색 API에 결과 부재 시 환각 방지 표준 폴백 메시지 반환 적용 in `bteam/Oliview_chatbot_b/project_ragapi.py`

**Checkpoint**: User Story 4 (올원챗 단독 웹 UI 서빙 및 RAG 검색) 독립 검증 완료

---

## Phase 7: User Story 5 - 통합 E2E 자동화 검증 테스트 스위트 구성 (Priority: P2)

**Goal**: 단일 스크립트 실행으로 5개 서비스(포털 랜딩, Pilos, Oliview, 올리챗, 올원챗)의 10대 핵심 체크포인트를 일괄 진단하고 상태 리포트를 출력하는 자동화 검증 스위트 제공

**Independent Test**: 터미널에서 `specs/003-e2e-service-stabilization/scripts/verify_e2e_services.ps1` 실행 시 10개 검증 항목 전체가 PASS로 판정되는지 확인

- [X] T019 [US5] 5개 서브시스템의 10대 핵심 체크포인트를 일괄 진단하는 `verify_e2e_services.ps1` 스크립트 작성 in `specs/003-e2e-service-stabilization/scripts/verify_e2e_services.ps1`
- [X] T020 [US5] `verify_e2e_services.ps1`에 공인 도메인(`https://ezenitac.duckdns.org`) 및 로컬 게이트웨이(`-Mode Local`, `http://localhost:8080`) 듀얼 타깃 스위치 기능 구현 in `specs/003-e2e-service-stabilization/scripts/verify_e2e_services.ps1`

**Checkpoint**: User Story 5 (통합 E2E 자동화 검증 스크립트) 준비 완료

---

## Phase 8: Polish & 종합 E2E 검증 (Cross-Cutting Concerns)

**Purpose**: 컨테이너 재빌드/재기동 및 전체 E2E 자동화 검증 10/10 PASS 달성

- [X] T021 [P] 게이트웨이 및 전체 서브서비스 컨테이너 재빌드/재기동 (`docker compose restart` 또는 `up -d`) in `docker-compose.yml`
- [X] T022 전체 E2E 자동화 스크립트(`verify_e2e_services.ps1`) 실행 및 10/10 PASS 검증 in `specs/003-e2e-service-stabilization/scripts/verify_e2e_services.ps1`
- [X] T023 [P] `specs/003-e2e-service-stabilization/quickstart.md` 기반 수동 시나리오 검증 및 최종 점검

---

## Dependencies & Execution Order

```mermaid
graph TD
    Phase1[Phase 1: Setup<br>T001-T003] --> Phase2[Phase 2: Foundational<br>T004-T005]
    Phase2 --> US1[Phase 3: User Story 1 (P1)<br>Pilos 404 해결<br>T006-T008]
    Phase2 --> US2[Phase 4: User Story 2 (P1)<br>Oliview 브랜드/SMTP<br>T009-T012]
    Phase2 --> US3[Phase 5: User Story 3 (P1)<br>올리챗 BGE-M3 HTTP<br>T013-T015]
    Phase2 --> US4[Phase 6: User Story 4 (P2)<br>올원챗 웹/RAG<br>T016-T018]
    
    US1 --> US5[Phase 7: User Story 5 (P2)<br>E2E 자동화 스크립트<br>T019-T020]
    US2 --> US5
    US3 --> US5
    US4 --> US5
    
    US5 --> Polish[Phase 8: Polish & E2E Run<br>T021-T023]
```

### Parallel Execution Opportunities

- **Phase 1**: T002 (docker-compose)와 T003 (scripts 디렉토리) 병렬 실행 가능
- **Phase 2**: T004 (Pilos 라우팅)와 T005 (게이트웨이 검증) 병렬 검증 가능
- **Phase 3**: T006 (`index.js`)와 T007 (`detail.js`/`chat.js`) 병렬 수정 가능
- **Phase 4**: T009 (`/api/brands`), T010 (`/api/search-brands`), T011 (`send-auth-code`) 병렬 수정 가능
- **Phase 5**: T013 (`06.02.app.py`)와 T014 (`03.hybrid_search.py`) 병렬 수정 가능
- **Phase 6**: T016 (`project_ragapi.py`)와 T017 (`index.html`) 병렬 수정 가능

---

## Implementation Strategy

### MVP First (User Story 1 Focus)
1. Phase 1 Setup 및 Phase 2 Foundational (Nginx 라우팅) 완료
2. Phase 3 User Story 1 (Pilos 404 해결 및 종목 상세 네비게이션) 구현 및 독립 검증 (MVP!)
3. Phase 4 ~ 6 (Oliview 브랜드/SMTP, 올리챗 HTTP 임베딩, 올원챗 웹 서빙) 점진적 구현
4. Phase 7 E2E 스크립트 작성 및 Phase 8 전체 자동화 검증 (10/10 PASS) 완결
