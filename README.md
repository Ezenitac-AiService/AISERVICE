# AISERVICE: 통합 AI 서비스 단일 진입 게이트웨이 및 보안 격리 플랫폼

> A-Team 및 B-Team의 데이터 분석 대시보드와 대화형 AI 챗봇 서비스를 단일 진입 도메인(HTTP 80) 및 단일 도커 네트워크(`aiservice-network`)로 통합한 AI 서비스 플랫폼입니다.

---

## 🏛️ 통합 아키텍처 개요

```
                       [ 클라이언트 브라우저 / 외부 요청 ]
                                       │ (HTTP 80)
                                       ▼
                 ┌───────────────────────────────────────────┐
                 │       aiservice-gateway (Nginx 1.25)      │
                 └─────┬──────────────┬──────────────┬───────┘
                       │              │              │
        ┌──────────────┴───┐          │          ┌───┴──────────────┐
        │  B-Team Services │          │          │  A-Team Services │
        ├──────────────────┤          │          ├──────────────────┤
        │ oliview_frontend │          │          │ pilos-web        │
        │ oliview_backend  │          │          │ pilos-db (MySQL) │
        │ oliview_chatbot_a│          │          └──────────────────┘
        │ oliview_chatbot_b│          │
        │ bteam_db (MySQL) │          │
        └──────────────┬───┘          │
                       │              ▼
                       │   ┌────────────────────────────────┐
                       └──►│ vllm-serv-gateway (vLLM Engine)│
                           │ - Fast: qwen3.5-2b             │
                           │ - Synthesis: qwen3.5-4b        │
                           │ - Embedding: bge-m3            │
                           │ - Reranker: bge-reranker-v2-m3 │
                           └────────────────────────────────┘
                           [ 내부 aiservice-network 격리 ]
```

---

## 🌐 단일 진입 URL 라우팅 맵

| 서비스 명 | 서브 URL 경로 | 백엔드 기술 스택 | 설명 |
|---|---|---|---|
| **통합 포털 랜딩** | `http://localhost:8080/` | Nginx Static HTML/CSS | 4대 AI 서비스 바로가기 카드 대시보드 |
| **B-Team Oliview** | `http://localhost:8080/bteam/oliview` | React Vite + Flask/Gunicorn | 화장품 리뷰 감정 분석 & 대시보드 |
| **B-Team 올리챗** | `http://localhost:8080/bteam/chata` | Streamlit | 실시간 뷰티 상담 챗봇 |
| **B-Team 올원챗** | `http://localhost:8080/bteam/chatb` | FastAPI / Uvicorn | 하이브리드 RAG 질의응답 챗봇 |
| **A-Team Pilos** | `http://localhost:8080/ateam/pilos` | Flask / Gunicorn | 주식 감정지수 분석 & 내장 챗봇 |

---

## 🚀 빠른 시작 (Quickstart)

### 1. 환경 설정 파일 준비
```bash
# 루트 디렉터리에서 실행
cp .env.example .env
```

### 2. 전체 시스템 원클릭 기동

- **Windows 환경**:
  ```cmd
  run_all_services.bat
  ```

- **Linux / macOS 환경**:
  ```bash
  chmod +x run_all_services.sh
  ./run_all_services.sh
  ```

- **Docker Compose 직접 실행**:
  ```bash
  docker compose up -d --build
  ```

### 3. 시스템 상태 확인
```bash
docker compose ps
```

---

## 🛡️ 핵심 보안 및 성능 가드레일

1. **외부 포트 100% 보안 격리**:
   - MySQL DBMS (포트 3306) 및 vLLM 서빙 게이트웨이 (포트 8081)의 외부 호스트 바인딩이 완전히 제거되어 외부 공격 노출을 원천 차단했습니다.
2. **Multi-tier LLM 다계층 라우팅**:
   - 일반 대화/의도 분류: 초경량 고속 `qwen3.5-2b` (초당 70+ 토큰)
   - 심층 RAG 분석/리포트 합성: 고품질 `qwen3.5-4b` (4,096 토큰 출력 지원)
3. **무지연 실시간 스트리밍**:
   - Nginx `proxy_buffering off;` 및 WebSocket/SSE 최적화로 LLM 토큰 생성 즉시 화면에 렌더링됩니다.
4. **대용량 DB 콜드스타트 보호**:
   - MySQL 헬스체크 `start_period: 60s`를 적용하여 대용량 백업 데이터 복구 완료 후 웹 서비스가 안전하게 기동됩니다.
