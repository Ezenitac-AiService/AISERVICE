# Feature Specification: 공인 DDNS 도메인(ezenitac.duckdns.org) HTTPS/Let's Encrypt 및 8080 게이트웨이 연동, 내부 백엔드·DB·LLM 연결 정상화 및 A-Team 파이프라인 워커 활성화

**Feature Branch**: `002-public-domain-duckdns-gateway`

**Created**: 2026-08-17

**Status**: Ready for Implementation

**Input**: User description: "ezenitac.duckdns.org 주소에 개발 플랫폼이 연결되었어. https://ezenitac.duckdns.org 및 http://ezenitac.duckdns.org (301 리다이렉트) 반영 완료. 각 웹 서버들이 페이지만 제대로 보여주고, 실제로 db와 llm 서버에 연결이 안되는 문제를 해결하고, ateam 수집/분석 워커를 상시 활성화해야 함."

## Clarifications

### Session 2026-08-17
- Q: 외부 사용자가 공인 포트 80과 내부 포트 8080/80 환경에서 어떻게 접속하며 리다이렉트 정책을 어떻게 확정할 것인가? → A: 포트 80(표준 HTTP)과 8080(비특권 대체 포트) 듀얼 바인딩을 지원하며, Nginx에 `port_in_redirect off;`를 적용하여 외부 포트 80 인입 시 불필요한 내부 포트 번호 노출 없이 `http://ezenitac.duckdns.org`로 매끄럽게 통신하도록 표준화함.
- Q: 공인 도메인(ezenitac.duckdns.org) 접속 시 HTTPS(SSL/TLS) 적용 범위를 어떻게 설정할 것인가? → A: Traefik Ingress 및 Let's Encrypt 자동 발급(CN=ezenitac.duckdns.org, 유효기간 ~2026-11-15)을 통해 표준 HTTPS(443) 보안 전송을 전면 적용하며, HTTP(80) 인입 시 HTTPS로 301 자동 리다이렉트되고 비특권 포트 8080 듀얼 바인딩을 함께 지원함.
- Q: A-Team의 수집·분석 통합 파이프라인(run_service_pipeline: 댓글수집→전처리→토큰화→일별문서→수급수집→Ridge추론→LLM보고서)을 어떤 환경에서 주기적으로 실행하고 관리할 것인가요? → A: `docker-compose`에 전용 파이프라인 워커(`pilos-worker`) 컨테이너를 추가하여 주기적으로 `pilos.jobs.run_service_pipeline`을 자동 실행하고, 실행 상태 및 단계별 소요 시간을 `service_pipeline_run` DB 테이블에 기록하여 웹 대시보드(`/api/pipeline/status`)와 실시간 연동함.
- Q: B-Team 올리챗(chata)의 BGE-M3 로컬 모델 미존재(FileNotFoundError) 및 올원챗(chatb)의 RAG API 404 통신 장애를 어떤 방식으로 정상화할 것인가요? → A: 모든 임베딩 및 RAG 추론 코드를 `vllm-serv-gateway`의 HTTP API(8090 포트) 원격 호출 방식으로 전면 리팩토링하고, 올원챗 프론트엔드의 API 엔드포인트를 게이트웨이 서브 경로(`/bteam/chatb/api/v1/search`)로 정규화함.
- Q: A-Team(pilos_v2.sql, 2.69GB) 및 B-Team(oliview_project_backup_0813.sql, 1.26GB)의 데이터베이스 초기 적재 및 DB명 설정을 어떻게 통합할 것인가요? → A: `docker-compose.yml`의 `docker-entrypoint-initdb.d`에 덤프를 마운트하여 첫 기동 시 자동 복원하고, DB명을 `pilos_v2` 및 `cosmetic_db`로 통합 일치화함.
- Q: A-Team pilos-worker의 파이프라인 자동 실행 주기 및 수동 실행 방식을 어떻게 구성할 것인가요? → A: 환경 변수(`PIPELINE_INTERVAL_SECONDS=600`, 기본값 10분) 기반 주기적 실행 루프로 동작하고, `docker exec pilos-worker python -m pilos.jobs.run_service_pipeline`을 통한 즉시 수동 트리거를 지원함.
- Q: 다중 페르소나 비판 검증에서 도출된 핵심 리스크(공인망 DoS로 인한 GPU VRAM 고갈, 대용량 DB 콜드스타트 타임아웃, Streamlit 웹소켓 장애)를 이번 v1 스펙의 필수 비기능 요구사항으로 즉시 통합할 것인가요? → A: 기능 우선 단계적 적용 원칙을 채택하여, 1단계에서는 공인 DDNS HTTPS/8080 게이트웨이 연동, 내부 백엔드·DB·LLM 연결 정상화, A-Team 파이프라인 워커 구동의 핵심 인프라 기능 구현 및 검증에 집중하고, 보안 Rate Limiting(DDoS 방어) 및 GPU VRAM 동적 튜닝은 2단계 운영 최적화 범위로 명확히 분리함.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 공인 HTTPS 도메인을 통한 통합 포털 단일 진입 (Priority: P1) 🎯 MVP

외부 네트워크(사외망, 모바일, 협력사)의 사용자가 웹 브라우저 주소창에 공인 DDNS HTTPS 도메인(`https://ezenitac.duckdns.org/` 또는 대체 포트 `http://ezenitac.duckdns.org:8080/`)을 입력하여 단일 진입 포털 랜딩 페이지에 즉시 접속하고, A-Team 및 B-Team의 4대 핵심 서비스 카드를 확인한 후 원하는 서비스로 이동할 수 있어야 한다. HTTP(80) 인입 시 HTTPS(443)로 자동 301 리다이렉트되어야 한다.

**Why this priority**:
내부 로컬호스트(`localhost`) 개발 환경을 넘어, 외부 테스터 및 이해관계자가 어디서나 표준 HTTPS 도메인을 통해 전체 AI 서비스 플랫폼에 안전하게 접근할 수 있도록 하는 핵심 진입 관문이다.

**Independent Test**:
외부 네트워크(LTE/5G 모바일 기기 또는 사외 PC)에서 브라우저를 열고 `https://ezenitac.duckdns.org/` 및 `http://ezenitac.duckdns.org/`으로 접속하여 HTTPS 세션 유지, 301 리다이렉트 및 통합 포털 카드가 렌더링되고 각 서브 서비스 링크가 올바르게 작동하는지 검증한다.

**Acceptance Scenarios**:
1. **Given** 외부 인터넷망에 연결된 클라이언트 브라우저에서, **When** `https://ezenitac.duckdns.org/`에 접속하면, **Then** 200 OK와 함께 유효한 Let's Encrypt SSL/TLS 인증서가 적용된 4개 서비스(B-Team Oliview, 올리챗, 올원챗, A-Team Pilos) 카드가 포함된 통합 포털 화면이 표시된다.
2. **Given** 클라이언트가 `http://ezenitac.duckdns.org/` (80 포트)로 접속하면, **When** HTTP 요청이 인입되면, **Then** 301 Moved Permanently와 함께 `https://ezenitac.duckdns.org/`로 자동 전환된다.
3. **Given** 통합 포털 랜딩 페이지가 표시된 상태에서, **When** 임의의 서비스 카드('입장하기', '대화 시작' 등)를 클릭하면, **Then** 동일 도메인의 서브 경로(`/bteam/oliview`, `/bteam/chata`, `/bteam/chatb`, `/ateam/pilos`)로 원활하게 이동한다.

---

### User Story 2 - 공인 HTTPS 도메인 기반 서브 서비스 및 AI 챗봇 무결성 통신 (Priority: P1)

외부 사용자가 공인 HTTPS 도메인을 통해 접속했을 때, Vite 기반 SPA 프론트엔드 자산 로딩, Streamlit WSS(보안 웹소켓) 연결, FastAPI 하이브리드 RAG 질의응답, Flask 대시보드 리포트 생성이 도메인 호스트명 변경에 영향받지 않고 완벽하게 Same-Origin 상태로 작동해야 한다. 올리챗 및 올원챗은 로컬 파일 의존성 없이 `vllm-serv-gateway`의 HTTP API(8090/8081)를 통해 임베딩 및 생성을 완결한다.

**Why this priority**:
HTTPS 환경에서도 모든 하위 애플리케이션의 API 호출, WSS 스트리밍, 임베딩/LLM 추론, CORS 정책이 일관되게 정상 작동해야 한다.

**Independent Test**:
외부 브라우저에서 `https://ezenitac.duckdns.org/bteam/chata` (올리챗) 및 `/bteam/chatb` (올원챗)에 접속하여 질문을 전송하고, 로컬 파일 누락 오류나 404 오류 없이 실시간 토큰 스트리밍 응답 및 RAG 검색 결과가 정상 수신되는지 확인한다.

**Acceptance Scenarios**:
1. **Given** 사용자가 `https://ezenitac.duckdns.org/bteam/oliview`에 접속했을 때, **When** 페이지 내 리뷰 감정 분석 및 대시보드를 탐색하면, **Then** 상대 경로 API(`/bteam/oliview/api`)를 통해 `bteam_db`(`cosmetic_db`)의 모든 데이터가 실시간 정상 로드된다.
2. **Given** 사용자가 `https://ezenitac.duckdns.org/bteam/chata`에 접속했을 때, **When** 뷰티 상담 질의를 입력하면, **Then** Traefik/Nginx WSS 프록시 및 `vllm-serv-gateway:8090`의 BGE-M3 HTTP 임베딩 API와 8081 LLM 추론을 거쳐 스트리밍 답변이 정상 출력된다.
3. **Given** 사용자가 `https://ezenitac.duckdns.org/bteam/chatb`에 접속했을 때, **When** 제품 분석 질의를 입력하면, **Then** 상대 경로 `/bteam/chatb/api/v1/search`를 통해 404 오류 없이 RAG 응답과 추천 상품 카드가 렌더링된다.
4. **Given** 사용자가 `https://ezenitac.duckdns.org/ateam/pilos`에 접속했을 때, **When** 종목별 수급 감정 지수를 조회하면, **Then** `pilos-web` 백엔드가 프록시 헤더를 올바르게 인식하고 `pilos_v2` DB로부터 최신 주식 지수 목록을 정상 렌더링한다.

---

### User Story 3 - A-Team 백그라운드 수집·분석 파이프라인 워커 상시 가동 및 상태 모니터링 (Priority: P1)

A-Team의 수집·분석 통합 파이프라인(`run_service_pipeline.py`)이 독립 워커 컨테이너(`pilos-worker`)에서 주기적(기본 10분 주기)으로 실행되어 최신 토스 댓글 수집, 전처리, Kiwi 토큰화, 일별 문서 생성, 수급 수집, Ridge v4 감정 추론, v13 LLM 보고서 생성을 자동으로 완결하고, 그 실행 이력을 `service_pipeline_run` 테이블에 기록하여 웹 대시보드(`/api/pipeline/status`)에 정상 노출해야 한다.

**Why this priority**:
A-Team Pilos 서비스의 핵심 가치인 실시간 감정 지수 및 자동화된 일별 LLM 리포트가 끊김 없이 생산되어야 하며, 웹 대시보드의 '서비스 데이터 갱신 상태 조회 실패' 장애를 근본적으로 해소해야 한다.

**Independent Test**:
1. `docker compose logs pilos-worker`를 통해 파이프라인이 주기적으로 7개 단계(수집→전처리→토큰화→일별문서→수급→Ridge추론→LLM보고서)를 완료하는지 확인한다.
2. `https://ezenitac.duckdns.org/ateam/pilos` 대시보드 상단에서 "서비스 데이터 갱신 상태" 카드가 `running` 또는 `completed`로 표시되고 세부 단계별 소요 시간이 실시간 표시되는지 검증한다.
3. `docker exec pilos-worker python -m pilos.jobs.run_service_pipeline`을 실행하여 온디맨드 수동 파이프라인 실행이 정상 완결되는지 확인한다.

**Acceptance Scenarios**:
1. **Given** `pilos-worker` 컨테이너가 기동된 상태에서, **When** 설정된 주기(`PIPELINE_INTERVAL_SECONDS=600`)가 도래하면, **Then** 백그라운드에서 `run_service_pipeline`이 순차 실행되고 `service_pipeline_run`에 `running` → `completed` 이력이 갱신된다.
2. **Given** 웹 대시보드(`https://ezenitac.duckdns.org/ateam/pilos`)를 열었을 때, **When** 상단 상태 카드가 로드되면, **Then** 500 에러 없이 최신 파이프라인 실행 상태(타겟 종목수, 토크나이저 버전, 소요시간 등)가 정상 렌더링된다.

---

### User Story 4 - B-Team 및 A-Team 대용량 데이터베이스 자동 초기화 및 무결성 연결 (Priority: P1)

통합 Docker Compose 환경 기동 시 B-Team(`oliview_project_backup_0813.sql`, 1.26GB) 및 A-Team(`pilos_v2.sql`, 2.69GB)의 SQL 덤프가 `/docker-entrypoint-initdb.d`를 통해 영속 볼륨에 자동 초기 적재되고, 모든 백엔드 웹/워커 컨테이너가 표준 DB 계정 및 올바른 DB 이름(`cosmetic_db`, `pilos_v2`)으로 오류 없이 통신해야 한다.

**Why this priority**:
웹 서버들이 페이지만 렌더링하고 실제 DB 연결에 실패하는 원인을 제거하여 영속 데이터 기반의 완전한 비즈니스 로직 서빙을 보장한다.

**Independent Test**:
`docker compose up -d` 후 각 DB 컨테이너(`bteam_db`, `pilos-db`)의 헬스체크가 healthy 상태에 도달하고, `verify_db.py` 및 Flask/FastAPI 헬스체크 엔드포인트가 200 OK를 반환하는지 확인한다.

**Acceptance Scenarios**:
1. **Given** `pilos_db` 컨테이너가 최초 생성될 때, **When** `/docker-entrypoint-initdb.d/01_pilos_v2.sql`이 실행되면, **Then** `pilos_v2` 데이터베이스 내 모든 테이블과 기존 데이터가 온전히 복원되고 `pilos-web` 및 `pilos-worker`가 정상 연결된다.
2. **Given** `bteam_db` 컨테이너가 최초 생성될 때, **When** `/docker-entrypoint-initdb.d/01_backup.sql`이 실행되면, **Then** `cosmetic_db` 데이터베이스가 복원되고 `oliview_backend`, `oliview_chatbot_a`, `oliview_chatbot_b`가 정상 연결된다.

---

### User Story 5 - 공인 IP 노출 환경에서의 데이터베이스 및 추론 엔진 철저 격리 (Priority: P2)

개발 플랫폼이 공인 IP(`1.250.5.161`) 및 DDNS 도메인(`ezenitac.duckdns.org`)에 직접 연결되더라도, 백엔드 DBMS(MySQL 3306, 3307)와 vLLM 추론 서버(8081, 8090, 8091)는 외부 공용 인터넷에서 어떠한 방식으로도 직접 접근되어서는 안 된다.

**Why this priority**:
공인 IP에 직접 노출된 서버 환경에서 데이터베이스 및 고비용 GPU 추론 엔진 포트가 개방될 경우 보안 침해 및 자원 고갈 위험이 발생하므로 강력한 사설 격리가 필수적이다.

**Independent Test**:
사외 터미널에서 `nmap` 또는 `curl`로 `ezenitac.duckdns.org:3306`, `ezenitac.duckdns.org:3307`, `ezenitac.duckdns.org:8081`, `ezenitac.duckdns.org:8090`에 직접 소켓 연결을 시도하여 100% `Connection Refused` 또는 타임아웃으로 차단되는지 검증한다.

**Acceptance Scenarios**:
1. **Given** 공인 인터넷에 노출된 서버 환경에서, **When** 외부 클라이언트가 `ezenitac.duckdns.org:3306` 또는 `:3307`로 직접 연결을 시도하면, **Then** 포트가 외부에 바인딩되어 있지 않아 연결이 즉시 거부(Refused)된다.
2. **Given** 외부 클라이언트가 `ezenitac.duckdns.org:8081` 또는 `:8090`으로 직접 HTTP 요청을 전송하면, **Then** 외부 포트가 닫혀 있어 요청이 도달하지 않는다.

---

### Edge Cases

- **도메인 호스트 헤더 불일치**: `Host: ezenitac.duckdns.org` 또는 `Host: 1.250.5.161`으로 접근 시 Vite 프론트엔드가 403 Forbidden을 반환하지 않도록 `allowedHosts` 설정이 포괄적으로 허용되어야 함.
- **슬래시 누락 URL 접근**: `https://ezenitac.duckdns.org/bteam/oliview`와 같이 끝에 슬래시(`/`)가 없는 URL 입력 시, Nginx/Traefik이 `https://ezenitac.duckdns.org/bteam/oliview/`로 HTTPS 프로토콜 유지 상태로 301 리다이렉트해야 함.
- **파이프라인 중복 실행 충돌 방지**: 워커의 스케줄러 실행 시 이전 배치가 진행 중인 경우 파일 잠금(`pilos-sentiment-index-service-pipeline.lock`) 및 DB status `running` 체크를 통해 중복 실행을 안전하게 스킵하고 로깅해야 함.
- **LLM/임베딩 서버 일시적 지연/오류**: `vllm-serv-gateway`가 응답하지 않을 경우 챗봇 및 워커가 명확한 에러 메시지와 재시도 정책을 적용하여 프로세스가 비정상 종료(Crash)되지 않아야 함.
- **초기 대용량 DB 적재 중 웹 요청 유입**: `docker-entrypoint-initdb.d` 적재 중(수 분 소요) 웹/워커 컨테이너가 기동되어 DB 연결 실패가 발생하지 않도록 `depends_on`의 `condition: service_healthy`를 엄격히 적용해야 함.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 게이트웨이 및 Traefik Ingress는 `ezenitac.duckdns.org`에 대한 HTTPS(443) 통신을 전면 수용하고, HTTP(80) 인입 시 HTTPS로 301 자동 리다이렉트하며 비특권 포트 8080 접속을 듀얼 지원해야 한다.
- **FR-002**: 게이트웨이는 외부 클라이언트의 접속 요청 시 `X-Forwarded-Host`, `X-Forwarded-Port`, `X-Forwarded-Proto`, `X-Real-IP`, `X-Request-ID` 헤더를 모든 백엔드 업스트림 서비스에 정확히 전달해야 한다.
- **FR-003**: B-Team Vite 프론트엔드 설정은 `ezenitac.duckdns.org` 및 공인 IP 호스트명 접속을 차단하지 않도록 호스트 허용 규칙(`allowedHosts: true`)을 유지해야 한다.
- **FR-004**: B-Team 프론트엔드 내의 모든 API 호출(Oliview 및 Chatbot-B)은 특정 도메인이나 절대 루트 경로로 고정되지 않고 올바른 게이트웨이 서브 경로(`/bteam/oliview/api/`, `/bteam/chatb/api/v1/search`)를 사용하여 Same-Origin을 유지해야 한다.
- **FR-005**: B-Team 챗봇(올리챗, 올원챗) 및 A-Team 내장 챗봇/워커는 로컬 임베딩 파일 직접 로드 방식 대신 내부 도커 네트워크 `http://vllm-serv-gateway:8090/v1` (BGE-M3 임베딩) 및 `http://vllm-serv-gateway:8081/v1` (Qwen LLM 추론) HTTP API를 원격 호출하여 처리해야 한다.
- **FR-006**: MySQL 데이터베이스(`bteam_db`, `pilos-db`) 및 Model Gateway(`vllm-serv-gateway`)는 외부 공인 포트 개방 없이 내부 사설 도커 네트워크(`aiservice-network`) 내에서만 통신해야 한다.
- **FR-007**: 리버스 프록시 리다이렉트 시 공인 포트 번호 및 프로토콜이 누락되어 `localhost:80`이나 비표준 포트로 이탈하지 않도록 `proxy_set_header Host $http_host;` 및 `proxy_redirect off;`, `port_in_redirect off;`를 철저히 준수해야 한다.
- **FR-008**: `docker-compose.yml`은 A-Team 파이프라인 전용 워커 서비스(`pilos_worker`)를 정의하고, 환경 변수 `PIPELINE_INTERVAL_SECONDS`(기본값 600)에 따라 주기적으로 `pilos.jobs.run_service_pipeline`을 실행해야 한다.
- **FR-009**: A-Team 파이프라인 워커는 각 단계(증분댓글수집, 전처리, Kiwi토큰화, 일별문서생성, 수급수집, Ridge추론, v13 LLM보고서생성)의 실행 상태 및 소요 시간을 `pilos_v2` DB의 `service_pipeline_run` 테이블에 기록해야 한다.
- **FR-010**: A-Team `pilos-web`은 `pilos_v2` 데이터베이스로부터 최신 지수 및 파이프라인 실행 상태를 정상 조회하여 `/api/pipeline/status` 및 `/api/stocks` 엔드포인트를 200 OK로 서빙해야 한다.
- **FR-011**: `docker-compose.yml`은 A-Team(`pilos_v2.sql`) 및 B-Team(`oliview_project_backup_0813.sql`) 덤프 파일을 각 DB 서비스의 `/docker-entrypoint-initdb.d/`에 마운트하여 컨테이너 최초 생성 시 자동 복원을 보장해야 한다.
- **FR-012**: 통합 오케스트레이터 스크립트(`run_all_services.bat`, `run_all_services.sh`) 및 Kubernetes Ingress(`ddns/ingress-ezenitac.yaml`)는 워커를 포함한 전체 10개 서비스(`gateway`, `vllm-serv`, `bteam_db`, `oliview_backend`, `oliview_frontend`, `oliview_chatbot_a`, `oliview_chatbot_b`, `pilos_db`, `pilos_web`, `pilos_worker`)의 HTTPS 기동, 정지, 상태 확인, 수동 파이프라인 트리거를 일괄 지원해야 한다.

---

### Key Entities & Microservices Map

- **Public DDNS Domain**: `https://ezenitac.duckdns.org/` (HTTPS 표준 진입점, Let's Encrypt SSL/TLS)
- **Public Alternate Port**: `http://ezenitac.duckdns.org:8080/` (비특권 공인 포트)
- **Host Public IPv4**: `1.250.5.161` (SK broadband 할당 공인 IP)
- **Ingress Controller**: Traefik (K3s / Rancher Desktop, 포트 80 및 443) ➔ `gateway-svc`
- **Internal Microservices Routing Map**:
  - `/` ➔ `gateway/html/index.html` (포털 메인 랜딩)
  - `/bteam/oliview/` ➔ `oliview_frontend:5173` (React SPA)
  - `/bteam/oliview/api/` ➔ `oliview_backend:5050` (Flask API ➔ `bteam_db:3306/cosmetic_db`)
  - `/bteam/chata/` ➔ `oliview_chatbot_a:8501` (Streamlit ➔ `vllm-serv-gateway:8090/8081`)
  - `/bteam/chatb/` ➔ `oliview_chatbot_b:8002` (FastAPI ➔ `vllm-serv-gateway:8090/8081`)
  - `/ateam/pilos/` ➔ `pilos-web:5000` (Flask 대시보드 ➔ `pilos-db:3306/pilos_v2`)
  - *(Internal Worker)* ➔ `pilos_worker` (백그라운드 파이프라인 ➔ `pilos-db` & `vllm-serv-gateway`)
  - *(Internal Gateway)* ➔ `vllm-serv-gateway:8081` (LLM), `:8090` (BGE-M3 Embedding), `:8091` (Reranker)

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 외부 인터넷 환경에서 `https://ezenitac.duckdns.org/` 접속 시 3초 이내에 Let's Encrypt HTTPS 세션과 함께 통합 포털 랜딩 페이지가 100% 정상 로드되어야 한다.
- **SC-002**: `http://ezenitac.duckdns.org/` (80 포트) 접속 시 `https://ezenitac.duckdns.org/` (443 포트)로 301 영구 리다이렉트되어야 한다.
- **SC-003**: 공인 HTTPS 도메인을 통한 4대 서브 서비스(`/bteam/oliview`, `/bteam/chata`, `/bteam/chatb`, `/ateam/pilos`) 접속 시 HTTP 상태 코드 `200 OK`를 기록하고 모든 정적 자산(JS/CSS/이미지)이 무결하게 로드되어야 한다.
- **SC-004**: HTTPS 접속 환경에서 올리챗 및 올원챗에 사용자 질의 전송 시 5초 이내에 `vllm-serv-gateway` HTTP API를 통한 첫 번째 스트리밍 토큰이 렌더링되고 4096 토큰 내에서 온전한 완결 답변이 생성되어야 한다.
- **SC-005**: 올원챗(`/bteam/chatb/`)에서 검색 요청 시 404 오류 없이 200 OK로 RAG 응답 및 추천 상품 목록이 정상 표시되어야 한다.
- **SC-006**: A-Team 대시보드(`/ateam/pilos/`) 접속 시 "서비스 데이터 갱신 상태 조회 실패"나 "전체 종목 정보 로드 실패" 오류 없이 `pilos_v2` DB의 최신 종목 목록 및 파이프라인 실행 상태 카드가 100% 정상 렌더링되어야 한다.
- **SC-007**: A-Team `pilos_worker` 컨테이너가 정상 기동되어 설정된 주기마다 7단계 파이프라인을 오류 없이 실행하고 `service_pipeline_run`에 실행 기록을 남겨야 한다.
- **SC-008**: 외부 공인 인터넷에서 포트 3306, 3307, 8081, 8090으로의 직접 접근 시도 시 100% 연결 거부(Connection Refused)되어 보안 무결성을 보장해야 한다.

---

## Assumptions

- DuckDNS 도메인 `ezenitac.duckdns.org`는 호스트의 현재 공인 IP `1.250.5.161`로 정상 라우팅되어 있다.
- Traefik Ingress Controller가 포트 80 및 443을 점유하며, Let's Encrypt SSL/TLS 인증서가 정상 발급되어 있다.
- `vllm-serv-gateway`는 내부 도커 네트워크 `aiservice-network`에서 8081(LLM), 8090(Embedding), 8091(Reranker) 포트로 서비스를 안정적으로 제공한다.
- 클라이언트는 표준 모던 웹 브라우저(Chrome, Safari, Edge, Firefox)를 사용한다.
