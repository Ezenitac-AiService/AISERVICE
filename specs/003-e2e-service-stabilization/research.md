# Phase 0 Research: E2E 서비스 안정화 및 서브서비스 종합 점검 (003-e2e-service-stabilization)

**Feature Branch**: `003-e2e-service-stabilization`  
**Created**: 2026-08-17  
**Spec**: [spec.md](file:///c:/AISERVICE/specs/003-e2e-service-stabilization/spec.md)

---

## 1. Pilos 종목 클릭 404 해결 및 Nginx 프록시 라우팅 동기화

### Decision
- **Nginx 게이트웨이 (`gateway/nginx.conf`)**:
  - `location /stocks/` 및 `location /about` 블록을 신설하여 `http://pilos-web:5000`으로 프록시 전달.
  - `location /api/`는 기존대로 `pilos-web:5000`으로 유지.
- **Pilos 프론트엔드 JavaScript (`index.js`, `detail.js`, `chat.js`)**:
  - 현재 브라우저 `window.location.pathname`이 `/ateam/pilos`로 시작하는지 감지하는 동적 베이스 경로 헬퍼 `getBaseUrl()` 구현.
  - 종목 카드 클릭 시 서브경로 환경이면 `/ateam/pilos/stocks/${code}`, 루트 환경이면 `/stocks/${code}`로 이동하도록 동적 생성.

### Rationale
- 사용자가 공인 도메인 서브경로(`https://ezenitac.duckdns.org/ateam/pilos/`)로 접속하든, 직접 링크나 로컬 포트(`http://localhost:5000/`)로 접속하든 404 없이 일관되게 페이지가 렌더링됩니다.
- Nginx 라우팅 추가와 클라이언트 동적 베이스 경로를 동시에 적용하여 단일 장애 지점을 제거하는 이중 안전망을 확보합니다.

### Alternatives Considered
- **대안 1**: Nginx 변경 없이 모든 JS 링크를 상대 경로(`stocks/${code}`)로만 변경.
  - *기각 사유*: URL 끝에 슬래시(`/`)가 누락된 경우(`/ateam/pilos`) 상대 경로가 상위 디렉토리로 잘못 해석될 위험이 있음.
- **대안 2**: Nginx에서 `/stocks/(.*)`를 `/ateam/pilos/stocks/$1`로 301 리다이렉트.
  - *기각 사유*: 불필요한 HTTP 라운드트립이 발생하고 브라우저 히스토리가 지저분해짐.

---

## 2. Oliview SMTP 이메일 인증 설정 및 예외 처리 정책

### Decision
- **환경 변수 주입 (`docker-compose.yml`, `.env`)**:
  - `oliview_backend` 서비스에 `SMTP_SERVER=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER=${SMTP_USER}`, `SMTP_PASSWORD=${SMTP_PASSWORD}`를 표준 환경 변수로 주입.
- **백엔드 예외 처리 (`bteam/Oliview_Project/backend/app.py`)**:
  - `@app.route('/api/send-auth-code')`에서 SMTP 연결/인증 에러(`smtplib.SMTPException`, `socket.error` 등) 발생 시 `500` 대신 `400 Bad Request` JSON 응답 반환.
  - 반환 메시지: `"이메일 발송에 실패했습니다. 메일 주소를 확인하거나 잠시 후 다시 시도해주세요."`
  - 서버 콘솔 로그에 상세 스택 트레이스(`traceback.print_exc()`) 기록.
  - `auth_codes_store` 딕셔너리에 인증번호 생성 시간(`created_at`), 만료 시간(TTL 5분), 실패 시도 횟수(`attempts` 최대 5회) 구조화 저장.

### Rationale
- 실제 SMTP 장애 시 사용자에게 서버 내부 오류가 아닌 실행 가능한 안내를 제공합니다.
- 메모리 내 단순 문자열 저장 대신 TTL과 시도 횟수 제한을 두어 브루트포스 공격 및 메모리 누수를 방지합니다.

### Alternatives Considered
- **대안 1**: SMTP 실패 시 개발/테스트용으로 인증번호를 프론트엔드 응답에 포함.
  - *기각 사유*: 보안상 치명적이며 운영 환경 누출 위험이 큼.

---

## 3. 올리챗 (ChatA) 로컬 BGE-M3 의존성 제거 및 HTTP 원격 임베딩 단일화

### Decision
- **임베딩 클라이언트 단일화**:
  - `bteam/Oliview_chatbot_a/common/embedding_client.py`의 `HttpBgeM3Embeddings`를 전 파이프라인(`06.02.app.py`, `05.chatbot.py`, `03.hybrid_search.py`, `02.search_chroma.py`)의 표준 임베딩 인터페이스로 채택.
  - `EMBEDDING_SERVER_URL` 환경 변수(`http://vllm-serv-gateway:8090/v1/embeddings`)를 우선 탐색하고, 로컬 디스크 파일 경로(`models/embeddings/bge-m3`) 탐색 및 SentenceTransformer 인스턴스화 시도를 전면 제거.
- **RAG 검색 결과 부재 시 폴백**:
  - ChromaDB 하이브리드 검색 결과가 없거나 임계값 이하일 때 LLM 환각 생성을 차단하고 `"관련 리뷰 데이터를 찾을 수 없습니다. 올리브영 등록 상품명으로 다시 검색해주세요."` 표준 안내문 출력.

### Rationale
- Docker 컨테이너 내부에 2.2GB 가중치 파일을 중복 마운트할 필요가 없어 이미지 빌드 및 컨테이너 기동 속도가 비약적으로 향상됩니다.
- vLLM 모델 서빙 게이트웨이(8090)의 CPU 전담 인스턴스를 공유함으로써 GPU VRAM을 절약하고 메모리 경합을 차단합니다.

### Alternatives Considered
- **대안 1**: 컨테이너 볼륨으로 BGE-M3 모델 폴더를 마운트하여 로컬 파이토치로 로드.
  - *기각 사유*: 프로세스마다 수백 MB의 CPU/GPU 메모리를 추가 점유하고 중복 로딩 발생.

---

## 4. 올원챗 (ChatB FastAPI) 정적 웹 서빙 및 라우팅 보장

### Decision
- **정적 서빙 마운트**:
  - `bteam/Oliview_chatbot_b/project_ragapi.py`의 `app.mount("/", StaticFiles(directory=".", html=True), name="static")` 유지.
  - FastAPI의 `root_path="/bteam/chatb"` 설정을 통해 Swagger UI 및 OpenAPI 문서가 Nginx 서브경로에서 정상 작동하도록 보장.
- **클라이언트 API 호출 경로**:
  - `index.html` 내 자바스크립트의 검색 API 호출 경로를 `/bteam/chatb/api/v1/search` 및 `api/v1/search` 상대 경로를 지원하도록 일치화.
- **RAG 환각 방지 폴백**:
  - 검색 결과가 없을 경우 허위 리뷰 생성을 방지하는 표준 메시지 반환.

### Rationale
- 올원챗 단독 사용자 화면(`https://ezenitac.duckdns.org/bteam/chatb/`) 접속 시 404 없이 즉시 인터페이스가 제공되고 검색이 원활하게 동작합니다.

---

## 5. Oliview 브랜드 조회 및 검색 API 일원화 (`GET /api/brands`)

### Decision
- **백엔드 엔드포인트 구현 (`bteam/Oliview_Project/backend/app.py`)**:
  - `@app.route('/api/brands', methods=['GET'])` 구현.
  - `keyword = request.args.get('keyword', '').strip()` 파라미터 처리:
    - `keyword`가 없을 경우: `SELECT brand_id, brand_name, brand_code FROM brands WHERE is_active = 1` 실행하여 3,062개 전체 브랜드 목록 반환.
    - `keyword`가 있을 경우: `SELECT brand_id, brand_name, brand_code FROM brands WHERE is_active = 1 AND (brand_name LIKE %s OR brand_code LIKE %s)` 실행하여 필터링 반환.
  - 기존 `@app.route('/api/search-brands', methods=['GET'])`는 `@app.route('/api/brands')`를 호출하는 프록시/별칭으로 유지.

### Rationale
- 프론트엔드의 `CompetitorDashboardPage`(`/api/brands`)와 `LoginPage`(`/api/search-brands`)가 모두 100% 정상 작동하도록 계약을 일원화합니다.

---

## 6. E2E 종합 자동화 검증 테스트 스위트 (`verify_e2e_services.ps1`)

### Decision
- **스크립트 위치**: `specs/003-e2e-service-stabilization/scripts/verify_e2e_services.ps1`
- **검증 대상 시나리오 (10개 세부 체크포인트)**:
  1. Root Portal Landing Page (`/`) HTTP 200 검증
  2. Pilos 메인 대시보드 (`/ateam/pilos/`) HTTP 200 검증
  3. Pilos 종목 상세 화면 (`/stocks/005930` 및 `/ateam/pilos/stocks/005930`) HTTP 200 검증
  4. Pilos 일별 리포트 API (`/api/stocks/005930/llm-reports`) 200 OK & JSON 데이터 검증
  5. Oliview 메인 프론트엔드 (`/bteam/oliview/`) HTTP 200 검증
  6. Oliview 브랜드 조회 API (`/bteam/oliview/api/brands`) 200 OK & 3,000개 이상 브랜드 검증
  7. Oliview 이메일 중복 체크 API (`/bteam/oliview/api/check-email`) 200 OK 검증
  8. 올리챗 (ChatA Streamlit) (`/bteam/chata/`) HTTP 200 검증
  9. 올원챗 (ChatB FastAPI) 정적 웹 (`/bteam/chatb/`) HTTP 200 검증
  10. 올원챗 RAG 검색 API (`/bteam/chatb/api/v1/search`) 200 OK & 추천 상품 JSON 검증
- **파라미터 지원**:
  - `-BaseUrl <string>` (기본값: `https://ezenitac.duckdns.org`)
  - `-Mode <string>` (`Public` / `Local` - `Local` 선택 시 `http://localhost:8080` 자동 지정)

### Rationale
- 단일 스크립트로 전체 시스템의 회귀 버그를 즉각 감지하고 배포 안정성을 수치화(10/10 PASS)할 수 있습니다.
