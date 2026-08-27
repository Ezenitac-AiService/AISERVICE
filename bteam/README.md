# Oliview B-Team 통합 개발 환경 (Blue / Green)

기존 `docker-compose.yml`과 원본 폴더는 **Blue** 기준선으로 유지한다. Feature 041의
Green은 코드·계약·공유 `packages/core`·uv workspace를 통합하지만 단일 컨테이너로
합치지 않는다. `pipeline_runner`, Dashboard backend/frontend, ChatA, ChatB 및
MySQL·Redis·ChromaDB는 각각 독립 컨테이너/의존 서비스다.

Green을 새로 만들고 검증·rollback rehearsal·최소 24시간 soak가 끝날 때까지 Blue
컨테이너, 네트워크, 볼륨, active Nginx upstream, 운영 데이터 endpoint는 유지한다.
외부 `CUTOVER_APPROVED` 없이는 운영 전환하지 않으며, 별도
`DECOMMISSION_APPROVED` 없이는 Blue를 중지·archive·삭제하지 않는다.

## Feature 041 Green 실행

```bash
cd bteam
# secret 값을 출력하지 않는 topology 검사
docker compose -f docker-compose.green.yml config --no-interpolate
# 외부 승인 전에는 VALIDATION만 사용하고, Green 전용 secret을 주입한다
docker compose -p bteam-green -f docker-compose.green.yml up -d --build
```

Green candidate 포트는 `127.0.0.1:15050`, `15173`, `18501`, `18002`이며 Blue의
운영 포트와 겹치지 않는다. candidate Nginx는 `deployment/nginx.green.conf`만
검증하고 active `gateway/nginx.conf`는 수정하지 않는다.

Green pipeline의 실제 리뷰 수집은 `CRAWLER_ENDPOINT`, 보고서 생성은
`MODEL_GATEWAY_ENDPOINTS` JSON 배열을 주입해야 한다. 기존 설정과의 호환을 위해
`GATEWAY_ENDPOINTS`도 alias로 허용하지만, 의존성이 없을 때는 fail-closed로
`FAILED` run만 남기고 성공으로 기록하지 않는다.

---

## 🏗️ 시스템 아키텍처 및 서비스 토폴로지

```mermaid
flowchart TB
    subgraph Host["호스트 머신 (Host Machine)"]
        Browser["웹 브라우저 (사용자 / 개발자)"]
    end

    subgraph MG_Net["model_gateway_default (도커 외부 네트워크)"]
        Gateway["vllm-serv-gateway\n:8081 (LLM 메인)\n:8090 (BGE-M3 임베딩)\n:8091 (리랭커)"]
    end

    subgraph BTeam_Net["bteam_net (도커 브리지 네트워크)"]
        DB["bteam_db\n(MySQL 8.0)\n:3306"]
        Backend["oliview_backend\n(Flask API)\n:5050"]
        Frontend["oliview_frontend\n(React 19 + Vite)\n:5173"]
        ChatbotA["oliview_chatbot_a\n(Streamlit)\n:8501"]
        ChatbotB["oliview_chatbot_b\n(FastAPI)\n:8002"]
    end

    Browser -->|:5173| Frontend
    Browser -->|:5050| Backend
    Browser -->|:8501| ChatbotA
    Browser -->|:8002| ChatbotB
    Browser -->|:8081| Gateway

    Frontend -->|/api 프록시| Backend
    Backend -->|SQL Query| DB
    ChatbotA -->|SQL Query| DB
    ChatbotB -->|SQL Query| DB

    ChatbotA -->|LLM & 임베딩| Gateway
    ChatbotB -->|LLM & 리랭킹| Gateway

    DB --- Volume[("bteam_mysql_data\n(Named Volume 영구 보존)")]
```

---

## 📌 서비스 및 포트 매핑 매트릭스

| 서비스명 | 디렉토리 경로 | 기술 스택 | 호스트 포트 | 역할 및 설명 |
|---|---|---|:---:|---|
| **`bteam_db`** | 루트 `oliview_project_backup_0813.sql` | MySQL 8.0 | `3306` | 공통 DB 인스턴스 (1.25GB 백업 자동 복원) |
| **`oliview_backend`** | `Oliview_Project/backend` | Flask 3.x | `5050` | 메인 백엔드 REST API & 이메일 인증 |
| **`oliview_frontend`** | `Oliview_Project/frontend` | React 19 + Vite | `5173` | 메인 사용자/관리자 웹 대시보드 UI |
| **`oliview_chatbot_a`** | `Oliview_chatbot_a` | Streamlit | `8501` | ChromaDB + Kiwi + RRF 하이브리드 검색 챗봇 |
| **`oliview_chatbot_b`** | `Oliview_chatbot_b` | FastAPI | `8002` | 경량 RAG 검색 API & 웹 UI |
| *(로컬 게이트웨이)* | `C:\AISERVICE\model_gateway` | vLLM / llama.cpp | `8081` (LLM)<br>`8090` (Embed)<br>`8091` (Rerank) | 로컬 LLM / 임베딩 / 리랭커 추론 서버 |

---

## 🚀 빠른 시작 가이드 (Quick Start)

### 1. 사전 준비
- Docker Desktop이 실행 중이어야 합니다.
- 로컬 Model Gateway 컨테이너(`vllm-serv-gateway`)가 구동 중이어야 합니다 (`curl http://127.0.0.1:8081/health`).
- 환경변수 파일 `.env`를 생성합니다 (기본 템플릿 제공):
  ```bash
  cp .env.example .env
  ```

### 2. 전체 서비스 일괄 빌드 및 상시 구동
```bash
# 전체 컨테이너(메인 웹 + DB + 챗봇 A + 챗봇 B) 빌드 및 백그라운드 구동
docker compose --profile all up -d --build

# 서비스 상태 확인
docker compose ps
```

### 3. 웹 서비스 접속 확인
- **메인 프론트엔드**: [http://localhost:5173](http://localhost:5173)
- **메인 백엔드 API**: [http://localhost:5050](http://localhost:5050)
- **챗봇 A (Streamlit)**: [http://localhost:8501](http://localhost:8501)
- **챗봇 B (FastAPI RAG)**: [http://localhost:8002](http://localhost:8002)

---

## 🧪 데이터베이스 접속 정보 (DB Credentials)

- **호스트**: 환경변수 `DB_HOST` (컨테이너 내부 Blue 기본값 `bteam_db`)
- **포트**: 환경변수 `DB_PORT`
- **데이터베이스명**: 환경변수 `DB_NAME`
- **서비스/관리자 계정**: 로컬 ignored `.env` 또는 외부 secret manager에서 주입
- **문자셋/콜레이션**: `utf8mb4` / `utf8mb4_0900_ai_ci`

비밀번호·토큰은 문서, 로그, inventory, checksum manifest에 기록하지 않는다.

---

## ⚙️ ML 및 데이터 배치 파이프라인 로컬 실행 (`uv`)

배치 스크립트는 `uv` 패키지 관리자를 통해 로컬에서 직접 실행할 수 있습니다:

```bash
# 1. 속성 기반 문장 분리 파이프라인 실행
cd Oliview_aspect_sentence_split
uv run python analyze_db_reviews.py --limit 10

# 2. 감정 분석 파이프라인 실행
cd ../Oliview_aspect_sentiment
uv run python analyze_db_sentiments.py --limit 10

# 3. LLM 요약 파이프라인 실행
cd ../Oliview_LLM
uv run python 02_llm_one_product_test_db.py
```

---

## 🛑 서비스 종료 및 정리

```bash
# 컨테이너 중지 (DB 볼륨 데이터는 영구 보존됨)
docker compose --profile all down

# Blue 운영 볼륨을 포함한 `down -v`는 사용하지 않는다. Green 검증 볼륨을
# 폐기해야 할 때에도 승인된 Green project와 명시된 Green volume만 대상으로 한다.
# 컨테이너 및 볼륨 완전 초기화 (operator 승인 범위에서만)
docker compose --profile all down -v
```
