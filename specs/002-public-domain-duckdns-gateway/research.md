# Research & Technical Decisions: 공인 DDNS 게이트웨이 및 내부 백엔드·DB·LLM 연결 정상화

**Feature Branch**: `002-public-domain-duckdns-gateway`  
**Date**: 2026-08-17  
**Spec**: [spec.md](file:///c:/AISERVICE/specs/002-public-domain-duckdns-gateway/spec.md)

---

## 1. Gateway Nginx 듀얼 포트 바인딩 및 서브경로 라우팅 (Dual-Port Gateway & Subpath Routing)

### Decision
Nginx 게이트웨이(`aiservice-gateway`)에 `listen 80`, `listen 8080` 듀얼 바인딩을 적용하고, `port_in_redirect off;`, `proxy_set_header Host $http_host;`, `proxy_set_header X-Forwarded-Host $host;` 설정을 적용하여 공인 DDNS(`ezenitac.duckdns.org`) 환경에서 포털 랜딩 및 4대 서브 서비스로 투명하게 라우팅한다.

### Rationale
- 외부 인터넷(LTE, 사외망)에서 사용자가 포트 번호 없이 `http://ezenitac.duckdns.org/`로 접근하거나 `:8080` 포트로 접근할 때 모두 동일한 단일 진입 포털 및 서브 경로로 접속할 수 있어야 한다.
- Nginx 기본 리다이렉트 동작은 내부 포트(80)를 반환하여 외부 클라이언트의 접속 포트(:8080)를 유실시키는 문제가 있으므로 `port_in_redirect off;`가 필수적이다.

### Alternatives Considered
- **포트 80 단일 바인딩**: 통신사 ISP(SK broadband 등)에 따라 주거용 회선에서 포트 80 인바운드가 차단되는 경우가 있어 단독 사용 시 접근성 리스크 발생.
- **포트 8080 단일 바인딩**: 브라우저 주소창에 포트 번호를 생략한 일반 사용자 요청이 유실됨.
- **최종 결정**: 80 및 8080 듀얼 바인딩으로 범용 접근성 보장.

---

## 2. B-Team 챗봇(올리챗, 올원챗) HTTP 임베딩 API 원격 호출 아키텍처 (HTTP Embedding Client)

### Decision
`Oliview_chatbot_a`(올리챗 Streamlit) 및 `Oliview_chatbot_b`(올원챗 FastAPI)의 로컬 BGE-M3 모델 파일 직접 로드 방식을 폐기하고, 내부 도커 네트워크 `http://vllm-serv-gateway:8090/v1/embeddings` (OpenAI 호환 API)를 호출하는 공통 HTTP 임베딩 클라이언트를 구현하여 ChromaDB 및 RAG 검색에 연동한다.

### Rationale
- 각 컨테이너 내부에서 BGE-M3 가중치 파일(수백 MB)을 직접 로드할 경우 로컬 경로 불일치(`FileNotFoundError: /app/models/embeddings/bge-m3`)가 발생하고 컨테이너마다 메모리/VRAM이 중복 소모된다.
- 이미 `model_gateway`(`vllm-serv-gateway`)가 포트 8090에서 BGE-M3 임베딩 서버(`llama-server`)를 데몬으로 구동 중이므로, HTTP API 호출을 통해 단일 모델 인스턴스를 공유하는 것이 메모리 효율 및 유지보수 측면에서 최선이다.

### Implementation Details
- **엔드포인트**: `POST http://vllm-serv-gateway:8090/v1/embeddings`
- **페이로드**: `{"model": "bge-m3", "input": ["검색 질의 또는 리뷰 텍스트"]}`
- **응답 규격**: 1024차원 Dense Embedding Vector 반환 (OpenAI 호환 포맷 `{"data": [{"embedding": [...]}]}`)
- **ChromaDB 연동**: ChromaDB의 커스텀 `EmbeddingFunction` 인터페이스를 구현하여 HTTP 클라이언트를 바인딩.

### Alternatives Considered
- **로컬 가중치 볼륨 마운트**: 각 컨테이너에 `./model_gateway/models/bge-m3`를 마운트하여 PyTorch/Transformers로 개별 로드. 컨테이너 기동 지연 및 메모리 중복 낭비로 기각.

---

## 3. 올원챗(`oliview_chatbot_b`) 프론트엔드 API 엔드포인트 게이트웨이 정규화 (Subpath Normalization)

### Decision
`bteam/Oliview_chatbot_b/index.html` 내 `const API_URL = "/api/v1/search";`를 `/bteam/chatb/api/v1/search` (또는 상대 경로 `api/v1/search`)로 정규화하고, 백엔드 FastAPI에 `root_path="/bteam/chatb"`를 구성한다.

### Rationale
- Nginx 게이트웨이가 `/bteam/chatb/` 경로로 트래픽을 프록시할 때 프론트엔드 JS가 `/api/v1/search` 절대 경로를 호출하면 Nginx 루트(`/api/v1/search`)로 요청이 유입되어 404 Not Found가 발생한다.
- 상대 경로 또는 게이트웨이 서브 경로를 사용하여 Same-Origin 상태에서 200 OK 통신을 보장한다.

---

## 4. A-Team 백그라운드 수집·분석 파이프라인 전용 워커(`pilos_worker`) 컨테이너화 (Worker Daemon)

### Decision
`docker-compose.yml`에 `pilos_worker` 컨테이너를 추가하고, `pilos-sentiment-index` 환경에서 상주하며 환경 변수 `PIPELINE_INTERVAL_SECONDS`(기본값 600, 10분) 주기마다 `pilos.jobs.run_service_pipeline`을 실행하는 전용 워커 데몬(`pilos/jobs/worker_daemon.py`)을 구동한다.

### Rationale
- A-Team Pilos의 핵심 기능은 주기적 댓글 수집, 전처리, Kiwi 토큰화, 일별 문서 집계, 수급 수집, Ridge v4 추론, v13 LLM 보고서 생성이며, 그 실행 상태가 `service_pipeline_run` DB 테이블에 기록되어야 웹 대시보드의 상태 카드 오류(500)가 해결된다.
- 호스트 Windows 작업 스케줄러에 종속되지 않고 Docker Compose 내부에서 컨테이너 라이프사이클과 함께 상시 가동된다.
- 파일 잠금(`pilos-sentiment-index-service-pipeline.lock`)과 DB status 검사를 통해 중복 실행 충돌을 방어한다.
- `docker exec pilos-worker python -m pilos.jobs.run_service_pipeline`을 통한 온디맨드 즉시 실행도 완벽 지원한다.

---

## 5. 대용량 데이터베이스 자동 초기화 및 헬스체크 확장 (Database Auto-Init & Healthcheck)

### Decision
`docker-compose.yml`에서 A-Team(`pilos_v2.sql`, 2.69GB) 및 B-Team(`oliview_project_backup_0813.sql`, 1.26GB) 덤프 파일을 각 MySQL 컨테이너의 `/docker-entrypoint-initdb.d/`에 읽기 전용으로 마운트하고, `pilos_db` 헬스체크 설정을 `start_period: 300s`, `retries: 30`, `interval: 10s`로 확장한다.

### Rationale
- 대용량 SQL 덤프(2.69GB)는 최초 컨테이너 생성 시 복원에 약 3~5분이 소요되므로, 헬스체크 유예 기간(`start_period`)을 충분히 부여하지 않으면 웹/워커 컨테이너가 조기 기동하여 DB 연결 실패가 발생한다.
- DB명(`pilos_v2`, `cosmetic_db`)과 접속 계정/비밀번호를 `.env`와 완벽히 일치화하여 기동 즉시 무결한 DB 통신을 보장한다.

---

## 6. 통합 오케스트레이션 및 라이프사이클 관리 (Unified Orchestration)

### Decision
루트 `docker-compose.yml` 및 `run_all_services.bat`/`run_all_services.sh`를 갱신하여 총 10개 서비스(`gateway`, `vllm-serv`, `bteam_db`, `oliview_backend`, `oliview_frontend`, `oliview_chatbot_a`, `oliview_chatbot_b`, `pilos_db`, `pilos_web`, `pilos_worker`)를 단일 명령으로 빌드, 기동, 로그 조회, 중지할 수 있도록 통합한다.
