# Feature Specification: E2E 서비스 안정화 및 서브서비스 종합 점검 (003-e2e-service-stabilization)

**Feature Branch**: `003-e2e-service-stabilization`  
**Created**: 2026-08-17  
**Status**: In Review  
**Input**: User description: "e2e 테스트 구성 및, 각 프로젝트 점검 - pilos 종목 클릭 404 및 보고서 누락, oliview 로그인 브랜드 조회 실패, 올리챗 로컬 bge-m3 FileNotFoundError 및 LLM 연결 실패, 올원챗 /bteam/chatb/ 404 해결 + Oliview 회원가입 SMTP 이메일 인증 설정"

---

## Clarifications

### Session 2026-08-17
- Q: Oliview 회원가입 시 이메일 인증코드 발송에 필요한 SMTP 설정(Gmail)을 어떻게 주입하고 보장해야 하는가? → A: root `.env`, `.env.example` 및 `docker-compose.yml`의 `oliview_backend` 서비스에 `SMTP_SERVER=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER`, `SMTP_PASSWORD` 환경변수를 통합 주입하여 회원가입 시 인증번호 이메일 발송이 100% 정상 작동하도록 보장한다.
- Q: Oliview 회원가입 및 비밀번호 찾기 중 SMTP 서버 통신 장애나 인증 실패가 발생했을 때, 시스템은 어떤 방식으로 대응하고 사용자에게 알려야 합니까? → A: 클라이언트에 400 Bad Request JSON 응답(사용자 친화적 실패 안내 메시지)을 반환하고 백엔드 로그에 상세 에러를 기록한다.
- Q: 올리챗(ChatA) 및 올원챗(ChatB)에서 사용자가 검색한 상품이나 키워드가 데이터베이스에 없거나 유사도가 극히 낮을 때, 시스템은 어떤 방식으로 사용자에게 응답해야 합니까? → A: 허위 리뷰 생성을 방지하기 위해 안내 메시지("관련 리뷰 데이터를 찾을 수 없습니다. 올리브영 등록 상품명으로 다시 검색해주세요.")를 반환하여 환각을 원천 차단한다.
- Q: E2E 자동화 종합 검증 스크립트(`verify_e2e_services.ps1`)가 테스트할 기본 대상 호스트 및 실행 모드를 어떻게 구성해야 합니까? → A: 기본 공인 도메인(`https://ezenitac.duckdns.org`) 검증을 표준으로 하되, 파라미터(`-BaseUrl http://localhost:8080` 또는 `-Mode Local`)를 통해 로컬 게이트웨이 환경도 유연하게 점검할 수 있도록 지원한다.
- Q: Pilos 종목 클릭 시 발생하는 404 오류를 해결하기 위해 Nginx 게이트웨이 및 프론트엔드 라우팅 경로를 어떻게 동기화해야 합니까? → A: Nginx 게이트웨이에 `/stocks/` 및 `/about` 프록시 라우팅을 추가하고, Pilos 프론트엔드(`index.js`, `detail.js`)는 서브경로 prefix(`/ateam/pilos`)와 루트 경로를 자동 감지하는 동적 베이스 경로를 적용하여 이중 안전망을 구축한다.
- Q: Oliview 백엔드에서 3,062개 브랜드 조회 및 검색 API(`GET /api/brands` vs `GET /api/search-brands`)를 어떤 구조로 일원화 및 지원해야 합니까? → A: `GET /api/brands`를 표준 엔드포인트로 구현하여 `keyword` 쿼리 파라미터가 없으면 전체 3,062개 활성 브랜드를 반환하고 `keyword`가 있으면 일치 항목을 필터링 반환하며, 기존 `/api/search-brands`는 하위 호환성을 위한 별칭으로 유지한다.

---

## Ⅰ. User Scenarios & Testing *(mandatory)*

### User Story 1 - Pilos 종목 상세 페이지 및 챗봇 리포트 조회 (Priority: P1)

사용자가 Pilos 메인 대시보드(`https://ezenitac.duckdns.org/ateam/pilos/`)에서 종목 카드(예: 삼성전자 `005930`)를 클릭했을 때 404 에러 없이 종목 상세 화면(`/stocks/005930` 또는 `/ateam/pilos/stocks/005930`)으로 정상 진입하고, 대시보드 챗봇에서 기존 주가 및 감성 분석 리포트가 누락 없이 정상 출력된다.

**Why this priority**: 메인 페이지에서 개별 종목으로의 네비게이션과 LLM 분석 리포트 확인은 Pilos 서비스의 핵심 가치이며, 현재 404 및 데이터 누락으로 인해 사용자 경험이 완전히 차단되어 있습니다.

**Independent Test**:
1. 브라우저에서 `https://ezenitac.duckdns.org/ateam/pilos/` 접속 후 삼성전자(`005930`) 카드 클릭.
2. 종목 상세 페이지(`/stocks/005930` 또는 `/ateam/pilos/stocks/005930`)가 200 OK로 로드되고 일별 감성 지표 차트와 히스토리가 렌더링되는지 확인.
3. 챗봇 질문 블록에서 삼성전자 분석 리포트를 요청했을 때 최신 LLM 분석 보고서가 정상 응답되는지 확인.

**Acceptance Scenarios**:
1. **Given** Pilos 메인 대시보드가 열려 있을 때, **When** 사용자가 임의의 종목 카드를 클릭하면, **Then** Nginx 404 오류 없이 종목 상세 화면이 로드되고 과거 7일 이상의 감성 지표 히스토리가 표시된다.
2. **Given** 종목 상세 또는 메인 챗봇 창에서, **When** 사용자가 "삼성전자 분석 보고서 보여줘" 또는 고정 종목 질문 블록을 호출하면, **Then** "보고서가 없다"는 오류 대신 DB에 기저장된 LLM 리포트가 정상 반환된다.

---

### User Story 2 - Oliview 로그인 및 브랜드 고유 번호 조회 (Priority: P1)

사용자가 Oliview 메인 화면(`https://ezenitac.duckdns.org/bteam/oliview/`)에서 로그인 메뉴에 진입했을 때, 3,062개 등록 브랜드 목록 및 고유 코드(`brand_code`)가 드롭다운/검색 모달에 정상 표시되어 브랜드 관리자로 로그인하고 대시보드 기능을 이용할 수 있다.

**Why this priority**: 브랜드 조회가 실패하면 로그인 자체가 불가능하여 Oliview의 모든 하위 기능(리뷰 분석, 감성 통계, 경쟁사 비교 등)에 접근할 수 없습니다.

**Independent Test**:
1. 브라우저에서 `https://ezenitac.duckdns.org/bteam/oliview/login` 접속.
2. 브랜드 선택 입력창 클릭 시 3,062개 브랜드 목록이 검색되고 선택되는지 확인.
3. 로그인 완료 후 브랜드 대시보드로 정상 이동하는지 확인.

**Acceptance Scenarios**:
1. **Given** Oliview 로그인 페이지에 진입했을 때, **When** 프론트엔드가 브랜드 목록을 요청하면, **Then** `/bteam/oliview/api/brands` 엔드포인트가 200 OK로 3,000개 이상의 브랜드 데이터를 반환하여 화면에 즉시 렌더링된다.
2. **Given** 브랜드(예: '구달')를 선택했을 때, **When** 인증 및 로그인 버튼을 누르면, **Then** `oliview_project` DB의 `brand_accounts` 및 `brand_managers`와 연동되어 인증 세션이 정상 생성된다.

---

### User Story 3 - 올리챗 (Oliview ChatA) LLM & HTTP 임베딩 완전 연동 (Priority: P1)

사용자가 올리챗(`https://ezenitac.duckdns.org/bteam/chata/`)에서 올리브영 제품 분석 질문(예: "컬러그램 탕후루 탱글 꿀로스의 발림성 장단점을 분석해줘")을 입력했을 때, 로컬 모델 파일 경로 에러(`FileNotFoundError: /app/models/embeddings/bge-m3`) 없이 공통 임베딩/LLM 게이트웨이를 통해 정밀한 감성 분석 및 추천 답변이 스트리밍으로 출력된다.

**Why this priority**: 컨테이너 내부에 존재하지 않는 로컬 모델 파일 시스템 경로 참조로 인해 질의응답이 전면 중단되는 심각한 런타임 오류를 해결해야 합니다.

**Independent Test**:
1. 브라우저에서 `https://ezenitac.duckdns.org/bteam/chata/` 접속.
2. 채팅창에 "컬러그램 탕후루 탱글 꿀로스의 발림성 장단점을 분석해줘" 입력 후 전송.
3. 로컬 파일 에러 없이 ChromaDB 하이브리드 검색 및 Qwen LLM 분석 답변이 정상 생성되는지 확인.

**Acceptance Scenarios**:
1. **Given** 올리챗 Streamlit 인터페이스가 로드되어 있을 때, **When** 사용자가 제품 분석 질의를 전송하면, **Then** 컨테이너 내부 로컬 파일 대신 `vllm-serv-gateway:8090` HTTP 임베딩 클라이언트를 통해 벡터 검색이 정상 수행된다.
2. **Given** 벡터 검색 및 RAG 컨텍스트가 구성되었을 때, **When** LLM 생성을 요청하면, **Then** `vllm-serv-gateway:8081`을 통해 문맥에 맞는 올리브영 리뷰 분석 답변이 사용자 화면에 출력된다.

---

### User Story 4 - 올원챗 (Oliview ChatB) 단독 웹 인터페이스 서빙 및 라우팅 (Priority: P2)

사용자가 브라우저에서 `https://ezenitac.duckdns.org/bteam/chatb/`에 접속했을 때, Nginx 404 에러 없이 올원챗 전용 웹 인터페이스(`index.html`)가 즉시 렌더링되고, 검색 입력 시 `/bteam/chatb/api/v1/search`를 통해 하이브리드 RAG 검색 결과가 인터랙티브하게 표시된다.

**Why this priority**: 게이트웨이 서브경로 라우팅 매핑 누락으로 인한 404를 해결하여 웹 사용자가 직접 접근할 수 있도록 보장합니다.

**Independent Test**:
1. 브라우저에서 `https://ezenitac.duckdns.org/bteam/chatb/` 접속.
2. 올원챗 웹 UI가 200 OK로 표시되는지 확인.
3. 검색창에 "건성 피부 보습 앰플" 입력 후 추천 상품 및 AI 요약 답변이 렌더링되는지 확인.

**Acceptance Scenarios**:
1. **Given** 게이트웨이 Nginx가 실행 중일 때, **When** 브라우저가 `https://ezenitac.duckdns.org/bteam/chatb/`를 요청하면, **Then** 404 없이 `bteam/Oliview_chatbot_b/index.html`이 200 OK로 반환된다.
2. **Given** 올원챗 화면에서, **When** 검색어를 입력하고 검색을 실행하면, **Then** 상대 경로 또는 서브경로 prefix(`/bteam/chatb/api/v1/search`)로 API가 호출되어 추천 상품 리스트와 LLM 종합 답변이 표출된다.

---

### User Story 5 - 통합 E2E 자동화 검증 테스트 스위트 구성 (Priority: P2)

엔지니어 또는 관리자가 단일 스크립트 실행으로 4개 서브서비스(Pilos 대시보드/종목/리포트, Oliview 메인/브랜드/로그인, 올리챗 Streamlit/LLM, 올원챗 FastAPI/RAG)의 정상 동작 여부를 E2E 관점에서 일괄 검증하고 상세 상태 리포트를 수신한다. 기본값은 공인 도메인(`https://ezenitac.duckdns.org`)을 검증하며, 파라미터(`-BaseUrl` 또는 `-Mode Local`)를 통해 로컬 게이트웨이 환경 검증도 지원한다.

**Why this priority**: 기능 수정 시 각 서비스가 정상 연동되었는지 수동으로 반복 테스트하지 않고 즉각 검증할 수 있는 자동화된 테스트 안전망이 필요합니다.

**Independent Test**:
1. 터미널에서 `specs/003-e2e-service-stabilization/scripts/verify_e2e_services.ps1` (공인 도메인 대상) 및 `.\verify_e2e_services.ps1 -BaseUrl http://localhost:8080` (로컬 게이트웨이 대상) 실행.
2. 5개 서비스 엔드포인트 및 핵심 API 시나리오가 모두 PASS로 판정되는지 확인.

---

### Edge Cases
- 사용자가 URL 뒤에 슬래시(`/`)를 생략하고 `https://ezenitac.duckdns.org/stocks/005930` 또는 `https://ezenitac.duckdns.org/bteam/chatb`로 접근할 때 301 리다이렉트 또는 즉각 프록시 처리가 되는가?
- Chroma DB에 색인되지 않거나 유사도가 낮은 상품명을 올리챗/올원챗에서 검색했을 때 LLM 환각(허위 리뷰 생성) 없이 표준 안내 메시지("관련 리뷰 데이터를 찾을 수 없습니다. 올리브영 등록 상품명으로 다시 검색해주세요.")가 정상 출력되는가?
- LLM 응답 대기 시간이 10초 이상 소요될 때 게이트웨이 프록시 타임아웃(300s 설정)에 걸리지 않고 응답이 유지되는가?
- Oliview 이메일 인증번호 발송 중 Gmail SMTP 통신 장애나 자격증명 오류 발생 시, 프론트엔드가 무한 대기하지 않고 400 Bad Request 에러와 함께 사용자 안내 메시지("이메일 발송에 실패했습니다. 메일 주소를 확인하거나 잠시 후 다시 시도해주세요.")를 정상 표출하는가?

---

## Ⅱ. Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Nginx 게이트웨이는 Pilos의 종목 상세 경로(`/stocks/*`) 및 어바웃 페이지(`/about`)를 `pilos-web:5000`으로 누락 없이 프록시 라우팅해야 한다.
- **FR-002**: Pilos 프론트엔드 JavaScript(`index.js`, `detail.js`, `chat.js`)는 게이트웨이 서브경로(`/ateam/pilos`)와 루트 경로(`/`) 양쪽 환경 모두에서 `/api/` 및 `/stocks/` 화면 이동 요청이 404 없이 도달하도록 동적 베이스 경로(`/ateam/pilos` 자동 감지)를 적용하고 Nginx 프록시 경로와 완벽히 동기화해야 한다.
- **FR-003**: `pilos_v2` 데이터베이스는 `artifacts` (5번 모델 메타데이터), `stock` (10개 종목 기본 정보), `llm_report` (종목별 일별 분석 리포트), `sentiment_index_result` 데이터를 상시 유지하여 챗봇 및 상세 화면에서 500/404 에러 없이 조회가 가능해야 한다.
- **FR-004**: Oliview 백엔드(`oliview_backend`)는 `GET /api/brands` 엔드포인트를 구현하여 `keyword` 파라미터 유무에 따라 전체 3,062개 활성 브랜드 또는 필터링 결과를 반환해야 하며(기존 `/api/search-brands` 별칭 호환), 메인 프론트엔드(`oliview_frontend`)의 API 클라이언트는 게이트웨이 서브경로(`/bteam/oliview/api/`)를 표준으로 호출하여 로그인 및 대시보드에서 3,062개 브랜드 조회가 100% 정상 작동해야 한다.
- **FR-005**: Nginx 게이트웨이는 `location ^~ /bteam/oliview/api/`를 최우선 순위로 설정하여 프론트엔드 정적 SPA 라우팅에 가려지지 않고 `oliview_backend:5050/api/`로 직접 전달해야 한다.
- **FR-006**: B-Team 공통 DB(`bteam_db`)는 기존 영속 볼륨(`bteam_bteam_mysql_data`)의 실제 스키마인 `oliview_project`를 사용하며, 백엔드 및 챗봇 서비스의 `DB_NAME` 설정을 `oliview_project`로 일원화해야 한다.
- **FR-007**: 올리챗(ChatA)의 모든 파이썬 스크립트(`06.02.full_pipeline.py`, `05.chatbot.py`, `02.search_chroma.py`, `03.hybrid_search.py`)는 로컬 디스크의 `/app/models/embeddings/bge-m3` 가중치 파일 탐색을 전면 제거하고, `HttpBgeM3Embeddings`를 통해 `http://vllm-serv-gateway:8090/v1/embeddings` 엔드포인트를 호출해야 하며, 검색 결과 부재 시 허위 리뷰 생성을 차단하는 표준 폴백 안내문을 출력해야 한다.
- **FR-008**: 올원챗(ChatB FastAPI)은 `GET /` 및 `GET /bteam/chatb/` 요청 시 `bteam/Oliview_chatbot_b/index.html` 정적 페이지를 정상 서빙해야 하며, 하이브리드 RAG 검색 결과가 없을 경우 환각을 방지하는 표준 폴백 안내 메시지를 응답해야 한다.
- **FR-009**: 모델 게이트웨이(`vllm-serv-gateway`)는 임베딩(8090) 및 리랭커(8091) 인스턴스를 CPU 전담(`--n_gpu_layers 0`)으로 구동하고, 메인 LLM(8089/8081)만 GPU VRAM에 적재하여 총 GPU VRAM 점유율을 4.0GB 미만으로 통제해야 한다.
- **FR-010**: 전체 4대 서브시스템의 핵심 E2E 시나리오(Pilos 종목/리포트, Oliview 브랜드조회, 올리챗 RAG 생성, 올원챗 RAG 검색)를 검증하는 자동화 테스트 스크립트(`verify_e2e_services.ps1`)를 제공해야 하며, 공인 도메인 및 로컬 게이트웨이(`-BaseUrl`) 타깃 전환을 지원해야 한다.
- **FR-011**: Oliview 백엔드(`oliview_backend`)는 회원가입 및 비밀번호 재설정 시 이메일 인증 코드를 정상 발송할 수 있도록 `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` 환경 변수를 컨테이너 환경에 전달받아 안전하게 발송하며, SMTP 통신/인증 실패 시 `400 Bad Request` 에러 응답과 친절한 실패 안내 메시지를 반환하고 서버 로그에 상세 에러를 기록해야 한다.

### Key Entities

- **StockDetailContext**: 종목 코드, 한글 종목명, 최신 감성 지수, 과거 7일간의 지수 변동 내역 및 일별 LLM 분석 요약문.
- **BrandMetadata**: 브랜드 ID, 브랜드 공식 명칭, 고유 브랜드 코드(`brand_code`), 활성 상태 플래그.
- **EmbeddingClientRequest**: 텍스트 쿼리 문자열을 수신하여 1024차원 고차원 밀집 임베딩 벡터로 변환하는 HTTP 요청 DTO.
- **RagSearchResult**: 사용자 질의에 대한 ChromaDB 하이브리드 검색 문서, 리랭킹 스코어, 상위 추천 상품 목록 및 LLM 종합 추천 답변.

---

## Ⅲ. Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Pilos 메인 화면에서 10개 종목 중 임의의 종목을 클릭했을 때 종목 상세 화면 및 감성 지수 차트가 1.5초 이내에 200 OK로 표시된다.
- **SC-002**: Pilos 챗봇에서 삼성전자 등 등록 종목의 분석 리포트 조회 시 "보고서 없음" 오류 없이 기존 보고서가 100% 정상 출력된다.
- **SC-003**: Oliview 로그인 화면 진입 시 3,062개 브랜드 데이터가 1초 이내에 로드되어 브랜드 선택 및 로그인이 100% 성공한다.
- **SC-004**: 올리챗(ChatA)에서 제품 분석 질문 전송 시 `FileNotFoundError` 발생율 0% 및 LLM 분석 답변이 10초 이내에 완결된다.
- **SC-005**: 올원챗(ChatB) 웹 주소(`https://ezenitac.duckdns.org/bteam/chatb/`) 접근 시 404 없이 인터페이스가 100% 렌더링되고 RAG 검색이 성공한다.
- **SC-006**: 3개 모델 동시 상주 상태에서 시스템 GPU VRAM 사용량이 4.0GB 이하로 유지된다.
- **SC-007**: E2E 통합 검증 스크립트(`verify_e2e_services.ps1`) 실행 시 10개 검증 항목 전체가 PASS를 달성한다.
- **SC-008**: Oliview 회원가입 화면에서 이메일 인증번호 발송 요청 시 3초 이내에 200 OK를 반환하고 실제 인증메일이 대상 주소로 전송된다.

---

## Ⅳ. Assumptions

- Docker Desktop / WSL2 환경에서 GPU Passthrough(CUDA) 및 호스트 브리지 네트워크(`aiservice-network`)가 정상 작동한다.
- 외부 공인 도메인은 `https://ezenitac.duckdns.org`이며 Traefik Ingress를 통해 8080 게이트웨이 포트로 전달된다.
- B-Team 데이터베이스 볼륨(`bteam_bteam_mysql_data`)에는 `oliview_project` 스키마가 보존되어 있으며 `gp123` / `GP123!` 계정으로 접근 가능하다.
- A-Team 데이터베이스(`pilos_v2`)에는 10개 종목과 모델 v5 감성 분석 아티팩트 및 `llm_report` 데이터가 적재되어 있다.
