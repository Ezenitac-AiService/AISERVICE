# Feature Specification: 통합 AI 서비스 단일 진입 게이트웨이 및 서비스 보안 격리 리팩토링 (Unified AI Services Gateway & Isolation)

**Feature Branch**: `001-unified-services-gateway`

**Created**: 2026-08-17

**Status**: Draft

**Input**: User description: "리펙토링 작업을 할 스펙을 작성: 1. ateam 폴더(수집-전처리-분석-저장/웹/챗봇/DB), 2. bteam 폴더(수집-전처리-분석-저장-보고서/웹(프론트/백)/챗봇a/챗봇b/DB), 3. model_gateway 연결. 단일 도메인 하위 URL(ateam 메인, bteam 메인, 올리챗, 올원챗) 라우팅, DBMS 및 LLM 서버 외부 노출 차단 및 포트 통합, B-Team 메인 Oliview 내 챗봇 링크 주소 수정, CORS 및 하드코딩 점검, 3개 챗봇의 Multi-tier LLM 모델 라우팅(2B/4B), 통합 Nginx 전용 게이트웨이 컨테이너 구축 및 도커 네트워크 일원화, Gunicorn WSGI/ASGI 런타임 타당성 검증 및 적용, 10대 다중 페르소나 극한 심층 비판 검증 방어책 완비"

## Clarifications

### Session 2026-08-17
- Q: 서브 URL 경로 매핑 구조는 어떻게 지정되는가? → A: B-Team 메인은 `/bteam/oliview`, 올리챗은 `/bteam/chata`, 올원챗은 `/bteam/chatb`, A-Team 메인은 `/ateam/pilos`로 매핑한다.
- Q: 루트 경로(`/`)로 접속했을 때 어떤 화면 또는 동작으로 연결되어야 합니까? → A: 통합 포털 랜딩 페이지(AISERVICE Portal)를 제공하여 4개 서비스(A-Team Pilos, B-Team Oliview, 올리챗, 올원챗) 바로가기 카드 및 안내 화면을 표시한다.
- Q: B-Team 메인 Oliview UI 좌측 사이드바의 챗봇 바로가기 링크는 어떻게 수정되는가? → A: 하드코딩된 레거시 IP(192.168.x.x) 링크를 Nginx 게이트웨이 기준 통합 경로(올리챗: `/bteam/chata`, 올원챗: `/bteam/chatb`)로 수정한다.
- Q: 브라우저 CORS 오류 및 코드베이스 내 하드코딩된 주소/포트는 어떻게 처리하는가? → A: Nginx 단일 출처(Same-Origin) 라우팅과 백엔드 CORS 헤더 표준화를 통해 CORS 문제를 원천 차단하고, 소스코드 내 모든 레거시 IP/포트 하드코딩을 환경 변수(`.env`) 및 상대 URL 경로로 전면 리팩토링한다.
- Q: 3개 챗봇(A-Team 메인 챗봇, B-Team 올리챗, B-Team 올원챗)의 LLM 모델 라우팅 및 토큰 설정 정책은 어떻게 최적화되는가? → A: RAG/LangChain/LangGraph 파이프라인에서 일반 질의·의도분류·전처리 작업은 `qwen3.5-2b`(빠른 응답 + 8K~16K 컨텍스트)를 활용하고, 심층 리포트 요약 및 최종 고품질 RAG 답변 생성에는 `qwen3.5-4b`(4K~8K 컨텍스트)를 적용한다. 또한 기존 512~1024 수준으로 과도하게 낮게 제한된 최대 출력 토큰(`max_tokens`)을 2048~4096으로 상향 조정하여 온전한 컨텍스트 윈도우를 활용하도록 검토 및 정합화한다.
- Q: 통합 Nginx 게이트웨이 컨테이너 및 도커 네트워크 정리는 어떻게 구축되는가? → A: 최상위 레벨에 전용 Nginx 역방향 프록시 컨테이너(`gateway/` 디렉터리 기반 `aiservice-gateway`)를 신규 구축하여 포트 80을 전담하고, 기존에 분산/중복되었던 네트워크 브릿지(`bteam_net`, `model_gateway_default`)를 단일 통합 사설 네트워크(`aiservice-network`)로 완전 통합 정비한다.
- Q: Nginx와 백엔드(Flask, FastAPI, Streamlit) 사이에 Gunicorn 적용의 타당성과 위치는 어떠한가? → A: Gunicorn은 Nginx와 컨테이너 사이의 별도 중계 컨테이너가 아니라, Flask 컨테이너(`pilos-web`, `oliview_backend`) 내부의 프로덕션 WSGI 애플리케이션 서버(`gunicorn -w 2`)로 탑재하는 것이 모범 표준이다. FastAPI(`oliview_chatbot_b`)는 네이티브 비동기 ASGI 서버인 `uvicorn`을 적용하고, Streamlit(`oliview_chatbot_a`)은 자체 Tornado 웹소켓 서버를 네이티브로 실행하여 Nginx가 직접 프록시한다.
- Q: 10대 다중 페르소나 심층 비판(Windows 포트 80 충돌, 308 리다이렉트 포트 누출, 스트리밍 소켓 배압, 대용량 DB 콜드스타트 등)은 어떻게 방어하는가? → A: 1) `.env` 기반 `GATEWAY_PORT` 동적 바인딩, 2) `proxy_redirect off;` 및 `Host` 헤더 보존을 통한 내부 포트 누출 차단, 3) SSE gzip 우회 및 버퍼링 해제, 4) 클라이언트 단절 시 GPU 추론 조기 회수 로직을 전면 적용한다.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 통합 Nginx 역방향 프록시를 통한 단일 진입점 하위 URL 라우팅 및 통합 포털 (Priority: P1)

사용자 및 운영자는 복잡한 개별 포트 번호를 외울 필요 없이, 단일 진입 도메인(공통 HTTP 80 포트, 필요시 환경변수로 가변)의 체계적인 하위 URL 경로와 통합 포털 화면을 통해 A-Team 메인 웹, B-Team 메인 웹, 올리챗(Chatbot A), 올원챗(Chatbot B) 서비스에 접근할 수 있으며, B-Team 메인 화면 내 사이드바 링크를 통해 원활하게 챗봇으로 전환할 수 있다.

**Why this priority**: 현재 서로 다른 포트와 환경으로 분산되어 발생하는 접근 혼선과 포트 충돌을 해결하는 핵심 진입 인터페이스이므로 최우선 순위(P1)를 부여한다.

**Independent Test**: 신규 구축된 `aiservice-gateway` (Nginx) 컨테이너를 실행하고 브라우저에서 루트(`/`) 및 각 하위 URL로 접속했을 때, 포털 랜딩 페이지 및 해당 서비스의 화면/정적 리소스(JS, CSS, 이미지, 웹소켓)가 정상적으로 로드되는지 검증하고, B-Team 사이드바의 챗봇 버튼 클릭 시 올바른 하위 URL로 이동하는지 확인한다.

**Acceptance Scenarios**:

1. **Given** `aiservice-gateway` (Nginx) 서비스가 구동 중일 때, **When** 사용자가 루트 경로(`/`)로 접속하면, **Then** 4개 주요 서비스로 이동할 수 있는 통합 포털 랜딩 페이지가 표시된다.
2. **Given** `aiservice-gateway` 서비스가 구동 중일 때, **When** 사용자가 `/bteam/oliview`로 접속하거나 하위 페이지에서 새로고침(F5)을 누르면, **Then** 404 오류 없이 B-Team Oliview 메인 웹 애플리케이션 화면이 정적 에셋(CSS/JS)과 함께 정상 렌더링되고 Gunicorn 백엔드 API와 통신한다.
3. **Given** B-Team Oliview 메인 화면(`/bteam/oliview`)에서, **When** 좌측 사이드바의 '🤖 올리챗' 버튼을 클릭하면, **Then** `/bteam/chata`로 이동하여 올리챗(Streamlit) 인터페이스가 웹소켓 세션 끊김 없이 열린다.
4. **Given** B-Team Oliview 메인 화면(`/bteam/oliview`)에서, **When** 좌측 사이드바의 '🤖 올원챗' 버튼을 클릭하면, **Then** `/bteam/chatb`로 이동하여 올원챗(FastAPI/Uvicorn) 인터페이스가 열린다.
5. **Given** `aiservice-gateway` 서비스가 구동 중일 때, **When** 사용자가 `/ateam/pilos`로 접속하면, **Then** A-Team Pilos 메인 웹 대시보드(Gunicorn 기반) 화면이 정상 표시된다.

---

### User Story 2 - 총 3개 챗봇 및 RAG 파이프라인의 Multi-Tier LLM 연동 및 토큰 최적화 (Priority: P1)

총 3개의 챗봇(A-Team 메인 페이지 임베디드 챗봇, B-Team 올리챗, B-Team 올원챗) 및 RAG/LangChain/LangGraph 파이프라인에서 사용자가 요청을 보낼 때, 작업 난이도에 따라 `qwen3.5-2b`(빠른 응답)와 `qwen3.5-4b`(고품질 심층 답변) 모델을 적절히 라우팅하여 호출하고, Nginx 스트리밍 버퍼링 해제(`proxy_buffering off`)와 300초 타임아웃을 통해 답변이 중간에 잘리거나 504 게이트웨이 타임아웃 없이 실시간으로 완결 생성된다.

**Why this priority**: 챗봇의 핵심 기능성과 응답 품질, 체감 속도를 동시에 극대화하고 서버 리소스를 가장 효율적으로 활용하기 위한 필수 AI 서비스 계층 요구사항이다.

**Independent Test**: 각 챗봇(A-Team 챗봇, B-Team 올리챗, B-Team 올원챗)에서 일반 대화 및 복합 RAG 검색 질의를 각각 수행하고, 2B/4B 모델이 목적에 맞게 분기 호출되며 긴 길이의 답변도 온전하게 스트리밍 출력되는지 확인한다.

**Acceptance Scenarios**:

1. **Given** A-Team 메인 페이지(`/ateam/pilos`)에서, **When** 사용자가 종목 수급 및 감정 분석 챗봇에 질의하면, **Then** Model Gateway의 `qwen3.5-2b` 또는 `qwen3.5-4b`를 통해 풍부한 요약 보고서와 질의응답이 반환된다.
2. **Given** 올리챗(Chatbot A, `/bteam/chata`)에서, **When** 상품 리뷰 기반 실시간 상담을 진행하면, **Then** 임베딩(`bge-m3`) 및 Fast/Synthesis 모델 라우팅을 거쳐 토큰 잘림 및 타임아웃 없이 상세한 맞춤 추천 답변이 스트리밍된다.
3. **Given** 올원챗(Chatbot B, `/bteam/chatb`)에서, **When** 복합 RAG 질의를 입력하면, **Then** 하이브리드 검색 및 `qwen3.5-4b` 합성 모델을 통해 2,000자 이상의 상세 분석 답변이 정상 생성된다.

---

### User Story 3 - 내부 데이터베이스(DBMS) 및 LLM 서비스의 외부 접근 차단 및 단일 사설 네트워크 격리 (Priority: P2)

외부 공용 인터넷이나 권한 없는 클라이언트가 서비스 내부 데이터베이스(MySQL 3306/3307 포트 등) 및 LLM 추론 엔진(8081, 8000, 8090, 8091 포트 등)에 직접 접속하는 것을 원천 차단하고, 오직 통합 사설 Docker 네트워크(`aiservice-network`) 내에서만 컨테이너 간 사설 통신을 허용한다.

**Why this priority**: 데이터 유출 방지 및 LLM 리소스 무단 사용 차단 등 보안성 및 운영 안정성을 보장하기 위함이다.

**Independent Test**: 외부 호스트 환경에서 데이터베이스 포트 및 LLM 포트로 직접 소켓/HTTP 연결을 시도하여 연결이 거부(Connection Refused / Blocked)되는지 확인한다.

**Acceptance Scenarios**:

1. **Given** 통합 서비스가 가동 중일 때, **When** 외부 호스트에서 A-Team/B-Team MySQL 포트(3306 등)로 직접 연결을 시도하면, **Then** 포트가 공용 외부에 바인딩되지 않아 접속이 차단된다. (로컬 디버깅 목적 시 `127.0.0.1` 루프백으로만 한정)
2. **Given** 통합 서비스가 가동 중일 때, **When** 외부 호스트에서 Model Gateway 포트(8081, 8000 등)로 직접 HTTP 요청을 보내면, **Then** 외부 라우팅이 차단되고 오직 Nginx 역방향 프록시의 지정된 공개 경로만 접근 가능하다.
3. **Given** 내부 백엔드 컨테이너(`pilos-web`, `oliview_backend`, `oliview_chatbot_a`, `oliview_chatbot_b`)에서는, **When** 내부 도커 서비스 도메인(`bteam_db`, `pilos-db`, `vllm-serv-gateway`)으로 통신하면, **Then** 단일 통합 네트워크(`aiservice-network`)를 통해 DNS 해석 및 상호 통신이 정상 수행된다.

---

### User Story 4 - 모듈형 실행 라이프사이클 및 대용량 DB 초기화 보호 (Priority: P3)

개발자 및 운영자는 전체 플랫폼(`gateway`, `model_gateway`, `ateam`, `bteam`)을 최상위 루트 오케스트레이션을 통해 한 번에 통합 구동할 수도 있고, 대용량 데이터베이스 덤프(2.7GB / 1.25GB) 초기화 지연 시간 동안 웹/챗봇 서비스가 비정상 종료(CrashLoop)되지 않고 헬스체크 완료 시점까지 안전하게 대기한 후 기동된다.

**Why this priority**: 서브시스템별 독립 개발 및 콜드 스타트 시점의 안정적인 런타임 복원력을 확보하기 위한 운영 지원 요구사항이다.

**Independent Test**: 빈 볼륨 상태에서 전체 시스템을 최초 기동하고, 대용량 DB 덤프 적재 완료 후 웹 및 챗봇 컨테이너가 정상적으로 연결되어 Healthy 상태로 진입하는지 확인한다.

**Acceptance Scenarios**:

1. **Given** Model Gateway가 먼저 기동된 상태에서, **When** B-Team 또는 A-Team을 나중에 기동하더라도, **Then** 단일 통합 네트워크(`aiservice-network`)를 자동으로 인식하여 별도의 수동 재설정 없이 정상 연결된다.
2. **Given** 전체 시스템을 최초 콜드 스타트할 때, **When** DB 컨테이너가 초기화 덤프를 적재하는 동안, **Then** `depends_on: condition: service_healthy` 대기 정책에 따라 백엔드/챗봇이 충돌 없이 순차 가동된다.

---

### Edge Cases

- **Windows 호스트 포트 80 충돌 방어**: Windows IIS, W3SVC, Skype 등으로 인해 포트 80이 이미 사용 중일 경우를 대비하여 `${GATEWAY_PORT:-80}:80` 환경 변수 방식을 기본 지원한다.
- **Flask 308/301 영구 리다이렉트 내부 포트 누출 방어**: Flask의 URL 끝 슬래시(`/`) 처리 시 내부 포트(`:5050`)로 리다이렉트되는 현상을 막기 위해 Nginx `proxy_redirect off;` 및 `proxy_set_header Host $http_host;`를 강제한다.
- **Nginx 스트리밍 버퍼링(SSE) 및 gzip 간섭 방어**: LLM 실시간 토큰 스트리밍 응답이 Nginx 버퍼나 gzip 압축 버퍼에 갇혀 실시간 타이핑이 지연되지 않도록 `proxy_buffering off;`, `gzip_types` 내 `text/event-stream` 제외, `proxy_read_timeout 300s;`를 필수로 적용한다.
- **WebSocket Connection Upgrade 맵핑**: Vite HMR 및 Streamlit 웹소켓의 동시 안정을 위해 Nginx 최상단 `map $http_upgrade $connection_upgrade { default upgrade; '' close; }` 디렉티브를 명시적으로 선언한다.
- **대용량 파일 업로드 413 오류 방어**: 사용자 리뷰 데이터셋(CSV) 및 이미지 업로드 시 Nginx 기본 1MB 제한으로 인한 413 오류를 방지하기 위해 `client_max_body_size 100M;`을 설정한다.
- **SPA 새로고침(F5) 404 방어**: B-Team React 프론트엔드가 `/bteam/oliview` 하위 경로에서 딥링크 또는 새로고침 시 404가 발생하지 않도록 Nginx location 내 `try_files $uri $uri/ /bteam/oliview/index.html;` 폴백을 적용한다.
- **CORS 및 인증 자격증명(Credentials) 정합성**: `allow_credentials=True` 환경에서 와일드카드 `*` 사용으로 인한 브라우저 차단을 방지하기 위해 단일 출처(Same-Origin) 라우팅을 우선하고 백엔드 CORS 헤더를 표준화한다.
- **FastAPI root_path 및 Swagger UI/정적 에셋 매핑**: 올원챗(FastAPI)을 `/bteam/chatb` 뒤에 배치할 때 `FastAPI(root_path="/bteam/chatb")`를 적용하여 대화형 UI 및 Swagger 문서의 정적 파일 경로가 깨지지 않도록 한다.
- **Flask ProxyFix 및 Gunicorn WSGI 런타임**: A-Team Pilos 및 B-Team Oliview 백엔드 Flask 웹 앱에 `gunicorn` 프로덕션 WSGI 서버와 `Werkzeug.middleware.proxy_fix.ProxyFix`를 적용하여 동시 요청 처리 안정성 및 서브 경로 렌더링을 보장한다.
- **대용량 DB 컨테이너 초기화 지연 방어**: 대용량 SQL 덤프(2.7GB / 1.25GB) 적재 시간을 고려하여 `start_period: 60s`, `retries: 20` 이상의 헬스체크 파라미터를 강제한다.
- **장애 격리 (Fault Isolation)**: Model Gateway 또는 특정 서브시스템이 일시 중단되더라도 Nginx 게이트웨이가 502/503 에러 페이지 대신 구조화된 안내 메시지를 반환하여 타 정상 서비스의 구동에 영향을 주지 않도록 격리한다.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 시스템은 전용 통합 Nginx 게이트웨이 디렉터리(`gateway/`) 및 컨테이너(`aiservice-gateway`)를 신규 구축하여 단일 공용 진입 포트(기본 HTTP 80)를 통해 전체 하위 서비스로 라우팅해야 한다.
- **FR-002**: 게이트웨이는 다음 경로에 대해 올바른 서비스 컨테이너로 요청을 라우팅/프록시해야 한다:
  - 루트 경로: `/` (통합 포털 랜딩 페이지 - 4개 서비스 바로가기 카드 UI 서빙)
  - B-Team 메인 웹 서비스: `/bteam/oliview` (프론트엔드 UI 및 백엔드 API 연동, SPA 새로고침 폴백 지원)
  - B-Team 올리챗 (Chatbot A): `/bteam/chata` (Streamlit 챗봇)
  - B-Team 올원챗 (Chatbot B): `/bteam/chatb` (FastAPI 챗봇)
  - A-Team 메인 웹 대시보드 및 챗봇: `/ateam/pilos` (Pilos Flask 웹 대시보드, 내장 챗봇 및 API)
- **FR-003**: Nginx 프록시는 올리챗(Streamlit) 및 프론트엔드 실시간 통신을 위한 WebSocket(`Upgrade`, `Connection: "upgrade"`) 및 SSE(Server-Sent Events) 스트리밍 프로토콜(`proxy_buffering off; proxy_read_timeout 300s;`)을 온전히 지원해야 한다.
- **FR-004**: 시스템은 단일 통합 내부 Docker 브릿지 네트워크(`aiservice-network`)를 생성하여 모든 서브시스템(`gateway`, `ateam`, `bteam`, `model_gateway`)이 컨테이너 서비스 이름(DNS)으로 통신하도록 구성하고 기존 중복 네트워크(`bteam_net`, `model_gateway_default`)를 전면 정리해야 한다.
- **FR-005**: `model_gateway`의 LLM 추론 서버(`vllm-serv-gateway`)는 호스트 포트(8081, 8000, 8090, 8091 등)를 외부에 공용 노출하지 않고, 내부 도커 네트워크를 통해서만 접근 가능해야 한다.
- **FR-006**: A-Team 및 B-Team의 데이터베이스 컨테이너(`pilos-db`, `bteam_db`)는 호스트 포트(3306, 3307 등)를 외부에 공용 바인딩하지 않고, 내부 도커 네트워크로만 격리되어야 한다 (로컬 디버깅 필요 시 `127.0.0.1` 루프백으로 한정).
- **FR-007**: B-Team의 챗봇 A/B 및 백엔드 애플리케이션의 LLM 접속 설정(`SERVER_HOST`, `LLM_BASE_URL` 등)은 내부 도커 서비스명인 `http://vllm-serv-gateway:8081` (또는 지정된 내부 포트)로 일원화되어야 한다.
- **FR-008**: A-Team의 웹/배치 애플리케이션의 LLM 접속 설정(`LLM_BASE_URL`, `EMBEDDING_BASE_URL`, `RERANK_BASE_URL`)은 내부 도커 네트워크 엔드포인트(`http://vllm-serv-gateway:8081`)로 일원화되어야 한다.
- **FR-009**: 전체 서비스를 일괄 실행 및 중지할 수 있는 통합 오케스트레이션 설정(루트 `docker-compose.yml` 및 통합 실행/종료 스크립트)을 제공해야 한다.
- **FR-010**: B-Team Oliview 프론트엔드 UI(`App.jsx`) 사이드바 내비게이션에 하드코딩된 레거시 IP 링크(`192.168.0.8:8501`, `192.168.0.152:8000`)를 게이트웨이 통합 상대 경로(`window.open('/bteam/chata', '_blank')`, `window.open('/bteam/chatb', '_blank')`)로 수정하여 단일 도메인 환경에서 끊김 없이 챗봇으로 연결되도록 해야 한다.
- **FR-011**: 시스템은 브라우저 상의 Cross-Origin Resource Sharing (CORS) 오류를 방지하기 위해 프론트엔드 API 호출을 단일 게이트웨이 동일 출처(Same-Origin) 경로(`/bteam/oliview/api`, `/ateam/pilos/api`)로 라우팅하고, Nginx 및 백엔드 프레임워크의 CORS 헤더를 표준화해야 한다.
- **FR-012**: 프론트엔드, 백엔드, 챗봇 모듈 내의 모든 하드코딩된 IP/호스트/포트 참조를 제거하고, 환경 변수(`.env`) 및 상대 URL 경로 기반으로 동적 해석되도록 리팩토링해야 한다.
- **FR-013**: 시스템은 3개 챗봇(A-Team 메인 챗봇, B-Team 올리챗, B-Team 올원챗) 및 분석 파이프라인에서 다계층 LLM 모델 라우팅(Multi-tier Routing)을 지원해야 한다 (일반 대화·전처리: `qwen3.5-2b`, 심층 문서 분석·최종 합성: `qwen3.5-4b`).
- **FR-014**: 양 팀의 RAG/LangChain/LangGraph 파이프라인 내 최대 출력 토큰(`max_tokens`) 및 컨텍스트 윈도우 버짓 설정을 Model Gateway 프로필에 맞추어 최소 2048~4096 토큰 수준으로 현실화하고 과도한 사전 잘림(Truncation)을 해소해야 한다.
- **FR-015**: Flask 백엔드 컨테이너(`pilos-web`, `oliview_backend`)는 단일 스레드 개발 서버 대신 프로덕션 WSGI 서버(`gunicorn -w 2 --timeout 120`)로 가동하고, FastAPI(`oliview_chatbot_b`)는 고성능 비동기 ASGI 엔진(`uvicorn`)으로 가동하여 런타임 안정성과 동시성 처리 성능을 확보해야 한다.
- **FR-016**: 대용량 SQL 덤프(2.7GB / 1.25GB) 초기화 시 콜드 스타트 지연을 방어하기 위해 DB 컨테이너 헬스체크에 충분한 초기 대기 시간(`start_period: 60s` 이상)을 적용하고, 종속 컨테이너는 헬스체크 완료 후 기동되도록 구성해야 한다.
- **FR-017**: Nginx 게이트웨이에 모든 인입 요청에 대한 고유 추적 ID(`X-Request-ID`) 주입 및 업스트림 처리 지연시간(`$upstream_response_time`)이 포함된 구조화된 JSON 액세스 로깅을 구성하여 분산 서비스 간 장애 추적성을 확보해야 한다.
- **FR-018**: Nginx 게이트웨이는 WebSocket 프로토콜 업그레이드 매핑(`map $http_upgrade $connection_upgrade`)을 명시하고, SSE(Server-Sent Events) 응답에 대해 gzip 압축을 우회하여 첫 토큰 응답 속도(TTFT)의 지연을 차단해야 한다.
- **FR-019**: 서브시스템 간 장애 격리(Fault Isolation) 정책을 적용하여 특정 서비스(예: A-Team 또는 Model Gateway)의 다운이나 재시작이 타 서비스(B-Team 메인 등)의 구동에 간섭하지 않도록 컨테이너 의존성 및 프록시 에러 처리를 독립화해야 한다.
- **FR-020**: 호스트 포트 충돌(Windows IIS 등)을 방지하기 위해 게이트웨이 포트를 `.env` 환경 변수(`GATEWAY_PORT`)로 동적 치환 가능하도록 구성하고, Flask 308 리다이렉트 시 내부 포트 노출을 방지하기 위해 Nginx `proxy_redirect off;` 및 `Host` 헤더 보존 정책을 적용해야 한다.
- **FR-021**: LLM 스트리밍 응답 도중 클라이언트 브라우저 탭 종료 시 불필요한 GPU 연산 낭비를 방지하도록 클라이언트 단절 감지(Client Disconnect) 처리 및 자원 반환 로직을 고려해야 한다.

### Key Entities

- **Nginx Gateway Architecture (`gateway/`)**:
  - `gateway/nginx.conf`: 단일 진입 라우팅, 업스트림 프록시 매핑, WebSocket `map`, SSE 버퍼링 해제(`proxy_buffering off`), 300초 타임아웃, `client_max_body_size 100M`, `proxy_redirect off;`, `X-Request-ID` 구조화 로깅 정책 정의.
  - `gateway/Dockerfile`: 경량 Alpine Nginx 기반 게이트웨이 이미지 정의.
  - `gateway/html/index.html`: 루트(`/`) 접속 시 서빙되는 통합 포털 랜딩 페이지 (카드 UI).
- **Application Server Runtime Stack**:
  - `Flask Web/API`: Gunicorn WSGI Server (멀티 워커 프로세스 관리, 타임아웃 방어)
  - `FastAPI RAG API`: Uvicorn ASGI Server (비동기 이벤트 루프 기반 I/O 처리)
  - `Streamlit Chatbot`: Native Streamlit Tornado Server (WebSocket 기반 상태 동기화)
- **Internal Service Network Topology**:
  - `aiservice-network`: 전체 4개 영역(`gateway`, `ateam`, `bteam`, `model_gateway`)이 공유하는 단일 표준 도커 브릿지 네트워크.
- **Service Endpoints & Upstream Mapping**:
  - `aiservice-gateway`: 통합 Nginx 역방향 프록시 (공용 포트 `${GATEWAY_PORT:-80}`)
  - `pilos-web`: A-Team 웹 애플리케이션 및 메인 챗봇 (Gunicorn, 내부 포트 5000, 경로 `/ateam/pilos`)
  - `oliview_frontend`: B-Team 프론트엔드 (내부 포트 5173 / 정적 빌드, 경로 `/bteam/oliview`)
  - `oliview_backend`: B-Team 백엔드 API (Gunicorn, 내부 포트 5050)
  - `oliview_chatbot_a`: 올리챗 Streamlit (Tornado, 내부 포트 8501, 경로 `/bteam/chata`)
  - `oliview_chatbot_b`: 올원챗 FastAPI (Uvicorn, 내부 포트 8002, 경로 `/bteam/chatb`)
  - `vllm-serv-gateway`: Model Gateway LLM/Embedding/Rerank (내부 포트 8081)
  - `pilos-db` & `bteam_db`: A/B-Team MySQL 데이터베이스 (내부 포트 3306)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 신규 구축된 통합 Nginx 게이트웨이(`aiservice-gateway`, 기본 포트 80)를 통해 통합 포털(`/`) 및 4개 핵심 사용자 서비스(`/bteam/oliview`, `/bteam/chata`, `/bteam/chatb`, `/ateam/pilos`) 모두 100% 정상 접속 가능해야 한다.
- **SC-002**: B-Team Oliview 메인 화면의 사이드바에서 '올리챗' 및 '올원챗' 버튼 클릭 시 100% 성공률로 해당 챗봇 하위 경로(`/bteam/chata`, `/bteam/chatb`)로 정상 이동해야 한다.
- **SC-003**: 3개 챗봇(A-Team 챗봇, B-Team 올리챗, B-Team 올원챗) 모두 일반 질의(2B)의 경우 2초 이내 첫 응답, 심층 RAG 합성(4B)의 경우 5초 이내 고품질 2,000자 이상 완결 답변 생성 성공률 100%를 달성해야 한다.
- **SC-004**: 외부 포트 스캔 및 직접 접속 시도 시 데이터베이스(3306/3307) 및 LLM 서비스(8081/8090/8091/8000) 포트에 대한 외부 직접 접근 차단율 100%를 달성해야 한다.
- **SC-005**: 전체 통합 환경 구동 시 서비스 간 포트 충돌로 인한 시작 실패율 0건을 유지해야 한다.
- **SC-006**: 신규 개발자가 단 하나의 통합 실행 명령으로 전체 환경을 3분 이내에 오류 없이 가동할 수 있어야 한다.
- **SC-007**: 브라우저 개발자 도구 콘솔에서 프론트엔드 API 호출 및 챗봇 통신 시 CORS 차단 에러 0건을 유지해야 한다.
- **SC-008**: 소스 코드 내 외부 사설 IP(`192.168.x.x`) 및 고정 로컬호스트 포트 하드코딩 잔재 0건을 달성해야 한다.
- **SC-009**: A-Team 및 B-Team의 RAG 토큰 설정에서 서버 지원 한도 미만의 불필요한 조기 잘림(Truncation) 발생률 0건을 달성해야 한다.
- **SC-010**: 도커 네트워크가 `aiservice-network` 단일 네트워크로 완전히 통합되어 레거시 네트워크(`bteam_net` 등) 잔재 0건을 달성해야 한다.
- **SC-011**: Flask 백엔드 서비스에 프로덕션 Gunicorn WSGI가 적용되어 동시 10개 이상의 동시 HTTP API 요청 처리 시 지연 및 연결 드롭 0건을 달성해야 한다.
- **SC-012**: 대형 RAG 생성(최대 120초 이상) 및 10MB 이상 데이터셋 업로드 시 Nginx 504 Timeout 및 413 Payload Too Large 오류 발생률 0건을 달성해야 한다.
- **SC-013**: 특정 서브시스템(예: A-Team 또는 Model Gateway) 장애 발생 시에도 무관한 타 서브시스템(B-Team 메인 등)의 가용성(Uptime) 100%를 유지해야 한다 (장애 전파 차단).
- **SC-014**: 스트리밍 응답(SSE) 시 gzip/프록시 버퍼링으로 인한 첫 토큰 지연 오버헤드 0ms를 달성해야 한다.
- **SC-015**: Windows 환경에서 포트 80 충돌 시 `.env`의 `GATEWAY_PORT` 변경만으로 10초 이내 포트 전환 가동 성공률 100%를 달성해야 한다.
- **SC-016**: API 호출 리다이렉트 시 브라우저에 내부 포트(5050, 5000 등) 노출 발생률 0건을 달성해야 한다.

## Assumptions

- **배포 인프라**: 로컬 개발 머신 또는 단일 호스트 서버 상에서 Docker Engine 및 Docker Compose를 기반으로 구동된다.
- **도메인 구조**: 별도의 다중 서브도메인이 아닌 단일 IP/호스트의 서브 패스(Sub-path) 기반 라우팅 방식을 사용한다.
- **보안 통제**: DBMS 및 LLM 서버는 호스트 외부 포트 포워딩을 제거하여 Docker 사설 네트워크 내에서만 컨테이너 간 통신이 이루어지도록 강제한다.
- **코드 무결성**: A-Team 및 B-Team의 내부 비즈니스 로직은 최대한 보존하며, 네트워크 통신 경로, 환경 변수(`.env`), Nginx 라우팅 및 Compose 설정 중심의 비파괴적 리팩토링을 적용한다.
