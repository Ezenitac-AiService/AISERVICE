# Data Model & Entity Specifications: 통합 AI 서비스 게이트웨이 및 서비스 격리

**Feature**: `001-unified-services-gateway`

**Date**: 2026-08-17

**Status**: Completed

---

## 1. 게이트웨이 라우팅 엔티티 (Gateway Route Entity)

Nginx 역방향 프록시가 관리하는 엔드포인트 및 업스트림 매핑 정의.

### Field Definitions

| 필드명 | 타입 | 필수 여부 | 설명 | 예시 값 |
|---|---|:---:|---|---|
| `route_id` | String | 필수 | 라우트 고유 식별자 | `bteam-oliview-frontend` |
| `path_pattern` | String | 필수 | 외부 인입 URL 매칭 패턴 | `/bteam/oliview/` |
| `upstream_target` | String | 필수 | 내부 Docker 서비스 DNS 및 포트 | `http://oliview_frontend:5173` |
| `rewrite_rule` | String | 선택 | URL 경로 리라이트 규칙 (정규화) | `break` 또는 `proxy_pass trailing slash` |
| `websocket_support` | Boolean | 필수 | WebSocket Upgrade 헤더 전달 여부 | `true` (Streamlit, Vite HMR) |
| `streaming_support` | Boolean | 필수 | SSE 버퍼링 비활성화 여부 | `true` (LLM / 챗봇) |
| `timeout_seconds` | Integer | 필수 | 프록시 읽기/쓰기 타임아웃 | `300` |
| `max_body_size` | String | 필수 | 클라이언트 바디 최대 허용 크기 | `100M` |

### Route Registry Table

```
Route Definitions:
├── [GET/POST] /                       -> gateway/html/index.html (통합 포털)
├── [ALL]      /bteam/oliview/api/     -> http://oliview_backend:5050/api/
├── [ALL]      /bteam/oliview/         -> http://oliview_frontend:5173/ (SPA Fallback)
├── [ALL/WS]   /bteam/chata/           -> http://oliview_chatbot_a:8501/bteam/chata/
├── [ALL]      /bteam/chatb/           -> http://oliview_chatbot_b:8002/
└── [ALL]      /ateam/pilos/           -> http://pilos-web:5000/
```

---

## 2. Multi-Tier LLM 모델 프로필 엔티티 (Model Context Profile Entity)

Model Gateway(`vllm-serv-gateway`)가 제공하고 챗봇이 분기 호출하는 모델 메타데이터 스키마.

### Field Definitions

| 필드명 | 타입 | 필수 여부 | 설명 | 예시 값 |
|---|---|:---:|---|---|
| `model_id` | String | 필수 | 모델 식별자 (API 호출 시 전달) | `qwen3.5-2b` / `qwen3.5-4b` |
| `tier_type` | Enum | 필수 | 모델 활용 계층 (`FAST`, `SYNTHESIS`, `EMBEDDING`, `RERANK`) | `FAST` (2B), `SYNTHESIS` (4B) |
| `recommended_context` | Integer | 필수 | 권장 컨텍스트 윈도우 크기 (Tokens) | `4096` |
| `max_context` | Integer | 필수 | 물리적 최대 컨텍스트 윈도우 (Tokens) | `34304` (2B), `11776` (4B) |
| `default_max_output_tokens` | Integer | 필수 | 기본 최대 생성 출력 토큰 | `2048` ~ `4096` |
| `base_vram_mb` | Integer | 필수 | 기본 모델 가중치 VRAM 점유량 (MB) | `1884` (2B), `3297` (4B) |

### Model Profile Mapping Table

| Model ID | Tier Type | 주 용도 | Context Length | Max Output Tokens | Base VRAM |
|---|:---:|---|:---:|:---:|:---:|
| `qwen3.5-2b` | `FAST` | 일반 대화, 의도 분류, 쿼리 재작성 | 4,096 ~ 32,768 | 2,048 | 1,884 MB |
| `qwen3.5-4b` | `SYNTHESIS` | 심층 RAG 분석, 고품질 감정 서술 리포트 | 4,096 ~ 11,776 | 4,096 | 3,297 MB |
| `bge-m3` | `EMBEDDING` | 다국어 고밀도/희소 벡터 임베딩 | 8,192 | N/A | 706 MB |
| `bge-reranker-v2-m3` | `RERANK` | 검색 문서 교차 인코더 정밀 재순위화 | 8,192 | N/A | 706 MB |

---

## 3. 서비스 환경 변수 엔티티 (Service Environment Entity)

각 마이크로서비스 컨테이너에 주입되는 일원화된 네트워크 및 런타임 환경 변수 스키마.

| 환경 변수명 | 적용 대상 | 설명 | 표준 주입값 |
|---|---|---|---|
| `GATEWAY_PORT` | `gateway` | 공용 진입 HTTP 포트 | `80` (호스트 포트 충돌 시 가변) |
| `SERVER_HOST` / `LLM_BASE_URL` | `chatbot_a`, `chatbot_b`, `pilos` | Model Gateway 내부 엔드포인트 | `http://vllm-serv-gateway:8081` |
| `FAST_LLM_MODEL` | 전체 챗봇/백엔드 | 고속 대화/전처리 모델명 | `qwen3.5-2b` |
| `SYNTHESIS_LLM_MODEL` | 전체 챗봇/백엔드 | 심층 합성/리포트 모델명 | `qwen3.5-4b` |
| `EMBEDDING_MODEL` | 전체 챗봇/백엔드 | 임베딩 모델명 | `bge-m3` |
| `RERANK_MODEL` | 전체 챗봇/백엔드 | 리랭커 모델명 | `bge-reranker-v2-m3` |
| `DB_HOST` | `pilos-web`, `oliview_backend` | MySQL 데이터베이스 호스트 | `pilos-db` / `bteam_db` |
| `DB_PORT` | `pilos-web`, `oliview_backend` | MySQL 내부 포트 | `3306` |
| `STREAMLIT_SERVER_BASE_URL_PATH` | `oliview_chatbot_a` | Streamlit 서브패스 접두사 | `bteam/chata` |
| `FASTAPI_ROOT_PATH` | `oliview_chatbot_b` | FastAPI 서브패스 접두사 | `/bteam/chatb` |
