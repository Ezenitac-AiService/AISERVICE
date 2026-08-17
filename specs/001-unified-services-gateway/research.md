# Research & Technical Decisions: 통합 AI 서비스 단일 진입 게이트웨이 및 서비스 보안 격리 리팩토링

**Feature**: `001-unified-services-gateway`

**Date**: 2026-08-17

**Status**: Completed

---

## 1. Nginx 전용 역방향 프록시 게이트웨이 아키텍처 (Gateway Architecture)

### Decision
최상위 프로젝트 루트에 전용 Nginx 컨테이너 디렉터리(`gateway/`)를 신규 생성하고, `gateway/nginx.conf`, `gateway/Dockerfile`, `gateway/html/index.html`을 배치하여 공용 HTTP 포트(기본 80, 가변 `${GATEWAY_PORT:-80}`)를 전담하도록 구성한다.

### Rationale
- **단일 책임 및 결합도 분리**: 각 서브팀(A-Team, B-Team, Model Gateway)의 컨테이너를 직접 외부에 노출하지 않고, 독립된 경량 게이트웨이 컨테이너(`aiservice-gateway`)가 SSL 종단, 헤더 정규화, 로깅, 라우팅을 전담함으로써 아키텍처 모듈성을 극대화한다.
- **경량성 및 고성능**: Alpine 기반 Nginx 이미지는 메모리 점유율이 15MB 미만으로 극도로 가볍고, C10K 동시 연결 및 프록시 처리에 최적화되어 있다.

### Alternatives Considered
- *Traefik / Envoy*: 라벨 기반 동적 라우팅이 가능하나, 본 프로젝트 규모에서 설정 복잡도가 과도하며 정적 카드 포털 HTML 서빙에 추가 컨테이너가 필요하여 기각(YAGNI 원칙).
- *호스트 OS Nginx 직접 설치*: 개발자 머신 환경에 따라 Nginx 설치/바이너리 차이가 발생하여 재현성이 떨어지므로 Docker 컨테이너화 채택.

---

## 2. 도커 네트워크 단일화 및 포트 보안 격리 (Network Topology & Isolation)

### Decision
기존의 파편화된 브릿지 네트워크(`bteam_net`, `model_gateway_default`)를 전면 폐기하고, 단일 사설 브릿지 네트워크 `aiservice-network`로 전체 9개 컨테이너를 통합한다. 또한 데이터베이스(`pilos-db`, `bteam_db`) 및 LLM 추론 서버(`vllm-serv-gateway`)의 호스트 `ports:` 매핑을 제거하여 외부 직접 접근을 100% 차단한다.

### Rationale
- **도커 DNS 해석 복원**: 컨테이너들이 서로 다른 브릿지에 쪼개져 있으면 `http://vllm-serv-gateway:8081`과 같은 컨테이너명 DNS 해석이 실패하여 챗봇이 LLM 서버에 연결하지 못하는 문제가 발생한다. 단일 네트워크 통합으로 컨테이너 간 무결한 사설 통신을 보장한다.
- **보안 격리**: DBMS(3306)와 vLLM(8081)의 외부 포트 포워딩을 제거하여 외부 무단 접속 및 악의적 추론 요청을 원천 차단한다.

### Alternatives Considered
- *Docker Host Network 모드 (`network_mode: host`)*: 포트 충돌 위험이 심각하고 Windows Docker Desktop 환경에서 완벽히 지원되지 않아 기각.
- *포트 번호 임의 변경 (예: 3308, 8089 등으로 분산 노출)*: 외부 스캐닝에 여전히 취약하고 포트 번호 관리 부담이 지속되므로 호스트 바인딩 완전 제거 채택.

---

## 3. 서브패스 라우팅 및 프레임워크별 어댑터 정책 (Sub-path Routing & Framework Adapters)

### Decision
Nginx에서 각 서브패스를 분기 프록시하고, 프레임워크별 특화 설정을 주입한다.

1. **루트 포털 (`/`)**: Nginx가 `gateway/html/index.html` 정적 웹 페이지를 직접 서빙.
2. **B-Team 메인 (`/bteam/oliview/`)**:
   - `oliview_frontend` (React/Vite): `vite.config.js`에 `base: '/bteam/oliview/'` 적용, Nginx에 `try_files $uri $uri/ /bteam/oliview/index.html;` 적용하여 브라우저 새로고침(F5) 404 방어.
   - `oliview_backend` (Flask API): `/bteam/oliview/api/` ➔ `http://oliview_backend:5050/api/`로 프록시.
3. **B-Team 올리챗 (`/bteam/chata/`)**:
   - `oliview_chatbot_a` (Streamlit): `STREAMLIT_SERVER_BASE_URL_PATH=bteam/chata` 및 Nginx `_stcore/stream` WebSocket Upgrade 헤더 전달.
4. **B-Team 올원챗 (`/bteam/chatb/`)**:
   - `oliview_chatbot_b` (FastAPI): `FastAPI(root_path="/bteam/chatb")` 및 Nginx `proxy_set_header X-Forwarded-Prefix /bteam/chatb;`.
5. **A-Team 메인 (`/ateam/pilos/`)**:
   - `pilos-web` (Flask): `Werkzeug.middleware.proxy_fix.ProxyFix` 및 Nginx `X-Forwarded-Prefix: /ateam/pilos`.

### Rationale
각 웹 프레임워크의 서브패스 인지(Path-Awareness) 메커니즘을 정확히 설정하지 않으면 정적 자산(CSS/JS) 404 및 WebSocket 연결 실패가 발생하므로, 프레임워크 표준 어댑터 방식을 적용한다.

---

## 4. 파이썬 웹/API 런타임 계층 (WSGI/ASGI Process Architecture)

### Decision
1. **Flask 백엔드 (`pilos-web`, `oliview_backend`)**: 프로덕션 WSGI 서버 `Gunicorn` 멀티 워커(`gunicorn -w 2 --timeout 120`)로 전환하여 실행.
2. **FastAPI 챗봇 (`oliview_chatbot_b`)**: 네이티브 비동기 ASGI 서버 `Uvicorn`(`uvicorn project_ragapi:app --host 0.0.0.0 --port 8002`)으로 실행.
3. **Streamlit 챗봇 (`oliview_chatbot_a`)**: 자체 Tornado WebSocket 런타임(`streamlit run 06.02.app.py`)으로 실행.

### Rationale
- Flask 개발 서버(Werkzeug)는 단일 스레드 기반으로 다중 사용자 동시 요청 시 병목이 발생하고 프로세스 크래시 시 복구되지 않는다. Gunicorn Pre-fork 워커가 멀티코어를 활용하고 프로세스 수명주기를 관리한다.
- FastAPI는 비동기 이벤트 루프(uvloop) 기반이므로 Uvicorn이 최적의 I/O 처리량을 제공한다.
- Streamlit은 WSGI/ASGI 표준이 아닌 커스텀 WebSocket 세션 엔진이므로 Gunicorn 래핑이 불가하며 네이티브 CLI 구동이 유일하고 올바른 방식이다.

---

## 5. Multi-Tier LLM 라우팅 및 토큰 예산 최적화 (LLM Routing & Token Budgeting)

### Decision
1. **다계층 모델 라우팅 (Multi-tier Routing)**:
   - **빠른 일반 대화, 의도 분류, 프롬프트 전처리**: `qwen3.5-2b` (VRAM ~1.9GB, 70+ tok/s, 컨텍스트 최대 32K+ 지원)
   - **심층 문서 분석, 최종 RAG 리포트 및 고품질 서술형 답변 합성**: `qwen3.5-4b` (VRAM ~3.3GB, 49 tok/s, 컨텍스트 최대 11K+ 지원)
   - **임베딩/리랭커**: `bge-m3` (8K 컨텍스트) / `bge-reranker-v2-m3` (8K 컨텍스트)
2. **토큰 설정 스케일링**:
   - `max_tokens` 설정을 기존 512~1024에서 **2048~4096**으로 현실화하여 장문 답변 조기 잘림(Truncation)을 해소.
   - Nginx `proxy_buffering off;`, `proxy_read_timeout 300s;` 및 `gzip` SSE 우회를 적용하여 실시간 토큰 스트리밍 체감 지연 0ms 유지.

### Rationale
- 전체 모델의 기본 VRAM 합산은 `1.9GB + 3.3GB + 1.4GB = 6.6GB`로, 개발 환경의 8GB(GTX 1070) 및 12GB(RTX 3060) GPU에서 KV Cache 여유 공간(2GB~5.4GB)을 온전히 확보하며 OOM 없이 동시 상주 가동이 가능하다.

---

## 6. CORS 및 하드코딩 제거 전략 (CORS & Zero-Hardcoding)

### Decision
1. **CORS 원천 해소**: Nginx가 프론트엔드와 백엔드 API를 동일한 오리진(`http://<host>/bteam/oliview/...`)으로 프록시하므로 브라우저 동일 출처 정책(Same-Origin)에 의해 CORS 차단이 원천 방지된다. 백엔드 CORS 헤더는 표준 화이트리스트로 보조 정합화한다.
2. **하드코딩 제거**:
   - `App.jsx` 내 사이드바 챗봇 버튼: `http://192.168.0.8:8501` ➔ `window.open('/bteam/chata', '_blank')`, `http://192.168.0.152:8000` ➔ `window.open('/bteam/chatb', '_blank')`
   - 프론트엔드 API Base: `http://${window.location.hostname}:5050` ➔ `/bteam/oliview/api` (상대 경로)
   - 챗봇/백엔드 LLM 서버 URL: `http://192.168.0.151:8081` ➔ `http://vllm-serv-gateway:8081` (`.env` 주입)

---

## 7. 대용량 DB 콜드스타트 및 장애 격리 (Cold-Start & Fault Isolation)

### Decision
1. **DB 콜드스타트 보호**:
   - MySQL 헬스체크에 `start_period: 60s`, `interval: 10s`, `retries: 20`을 적용하고, 백엔드/챗봇 컨테이너는 `depends_on: { db: { condition: service_healthy } }`로 순차 기동한다.
2. **장애 격리 (Fault Isolation)**:
   - Nginx의 업스트림 타임아웃 및 서브시스템별 독립 브릿지 통신을 통해 특정 서브시스템(예: A-Team) 다운 시에도 B-Team 등 타 서비스의 구동에 영향이 없도록 격리한다.
