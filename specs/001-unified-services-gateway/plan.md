# Implementation Plan: 통합 AI 서비스 단일 진입 게이트웨이 및 서비스 보안 격리 리팩토링 (Unified AI Services Gateway & Isolation)

**Branch**: `001-unified-services-gateway` | **Date**: 2026-08-17 | **Spec**: [spec.md](file:///c:/AISERVICE/specs/001-unified-services-gateway/spec.md)

**Input**: Feature specification from `specs/001-unified-services-gateway/spec.md`

## Summary

본 프로젝트는 A-Team(주식 감정 분석 웹/챗봇/DB), B-Team(화장품 리뷰 분석 웹/올리챗/올원챗/DB), Model Gateway(vLLM 기반 Qwen3.5 2B/4B, BGE 임베딩/리랭커)로 구성된 복합 AI 서비스 생태계를 단일 Nginx 게이트웨이(`gateway/`) 뒤로 통합하고, 단일 Docker 사설 네트워크(`aiservice-network`)로 일원화하여 외부 보안 격리를 달성하며, Multi-tier LLM 모델 라우팅 및 토큰 설정 확장을 통해 3개 챗봇의 성능과 응답 품질을 극대화하는 리팩토링 계획이다.

## Technical Context

**Language/Version**:
- Python 3.12 (A-Team Flask, B-Team Flask/FastAPI/Streamlit)
- Node.js 18+ / React 18+ (B-Team Oliview Vite Frontend)
- Nginx 1.25+ (Alpine Gateway)

**Primary Dependencies**:
- Web & Gateway: Nginx, Gunicorn 21.2+, Uvicorn, Streamlit, Werkzeug
- LLM & RAG: OpenAI Python SDK, FastAPI, ChromaDB, PyMySQL, LangChain/LangGraph
- Deep Learning & Serving: vLLM, Qwen3.5 2B/4B GGUF, BGE-M3, BGE-Reranker-v2-M3
- Database: MySQL 8.0

**Storage**:
- MySQL 8.0 (`pilos-db`, `bteam_db`) with named Docker volumes
- ChromaDB / Vector Store (`bteam/data/chroma_db`)
- GGUF Model Weight Cache (`model_gateway/models`)

**Testing**:
- Docker Compose Orchestration & Healthcheck validation
- Curl / HTTP integration tests for all sub-paths & API routes
- WebSocket & SSE streaming token latency verification
- Port isolation socket connection tests

**Target Platform**:
- Linux Docker Container Environment (Running on Windows WSL2 / Docker Desktop with NVIDIA GPU Acceleration)

**Project Type**:
- Microservices Web Application & AI Model Serving Gateway

**Performance Goals**:
- Fast LLM (2B): First token latency < 2.0s, Throughput > 60 tok/s
- Synthesis LLM (4B): Complete 2,000+ char report generation < 5.0s
- Gateway Routing Overhead: < 5ms p99 latency
- Zero CORS blockage & Zero 404 errors on SPA refresh

**Constraints**:
- External HTTP entry restricted exclusively to Port 80 (or configurable `${GATEWAY_PORT}`)
- Direct host access to MySQL (3306) and vLLM (8081) 100% blocked
- GPU VRAM footprint strictly constrained to <= 7.5GB for simultaneous 2B+4B+Embedding+Rerank serving

**Scale/Scope**:
- 9 Docker microservice containers across 4 sub-projects (`gateway`, `model_gateway`, `bteam`, `ateam`)
- 4 Primary user-facing web services (`/`, `/bteam/oliview`, `/bteam/chata`, `/bteam/chatb`, `/ateam/pilos`)
- 3 Integrated conversational AI chatbots

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Requirement & Evaluation | Status |
|---|---|:---:|
| **I. 언어 및 커뮤니케이션 정책** | 모든 대화, 질문, 답변, 산출물 문서(Markdown)는 한국어로 작성되며, 내부 생각(thinking)은 영어로 수행됨. | **PASS** |
| **II. TDD 및 계약 검증** | 게이트웨이 라우팅 규격(`gateway-routing-contract.md`) 및 LLM OpenAPI 계약(`llm-gateway-api.yaml`) 선제 정의 완료, 시나리오 검증 수립. | **PASS** |
| **III. 서비스 모듈화 및 격리** | 각 서브팀(`ateam`, `bteam`, `model_gateway`, `gateway`)의 디렉터리 독립성 유지, 단일 사설 네트워크를 통한 안전한 격리 보장. | **PASS** |
| **IV. 관측성 및 구조화 로깅** | Nginx `X-Request-ID` 주입 및 `$upstream_response_time` JSON 로깅 강제, 민감정보 마스킹 준수. | **PASS** |
| **V. 단순성 및 점진적 진화 (YAGNI)** | 복잡한 쿠버네티스/서비스메시 대신 Nginx + Docker Compose 표준 구성 채택, 점진적 설정 전환. | **PASS** |
| **품질 게이트 및 거버넌스** | Spec-Kit 수명주기(`Specify -> Plan -> Tasks -> Implement -> Verify`) 엄격 준수. | **PASS** |

## Project Structure

### Documentation (this feature)

```text
specs/001-unified-services-gateway/
├── spec.md              # Feature specification
├── plan.md              # Implementation plan (this file)
├── research.md          # Phase 0 technical decisions & rationale
├── data-model.md        # Phase 1 data models & entity mapping
├── quickstart.md        # Phase 1 verification & run guide
├── contracts/           # Phase 1 interface contracts
│   ├── gateway-routing-contract.md
│   └── llm-gateway-api.yaml
├── checklists/
│   └── requirements.md  # Spec quality checklist (16/16 pass)
└── tasks.md             # Phase 2 output (/speckit-tasks command)
```

### Source Code Architecture (repository root)

```text
c:\AISERVICE/
├── docker-compose.yml              # [NEW/MODIFY] 최상위 통합 오케스트레이션 Compose
├── .env.example                    # [NEW/MODIFY] 통합 환경 변수 템플릿
├── gateway/                        # [NEW] 전용 Nginx 통합 게이트웨이
│   ├── Dockerfile
│   ├── nginx.conf                  # 단일 진입 라우팅, WS/SSE, CORS, 타임아웃 300s 설정
│   └── html/
│       └── index.html              # 루트(/) 통합 포털 랜딩 페이지 (카드 UI)
├── model_gateway/                  # [MODIFY] LLM 서빙 계층 (포트 8081 외부 바인딩 제거)
│   ├── docker-compose.yml
│   └── config/                     # Multi-tier 2B/4B/BGE 컨텍스트 프로필
├── bteam/                          # [MODIFY] B-Team 서브시스템
│   ├── docker-compose.yml          # 포트 정리, aiservice-network 통합
│   ├── Oliview_Project/
│   │   ├── frontend/
│   │   │   ├── vite.config.js      # base: '/bteam/oliview/' 적용
│   │   │   └── src/App.jsx         # 상대경로 API 및 챗봇 버튼 링크 리팩토링
│   │   └── backend/
│   │       ├── Dockerfile          # Gunicorn WSGI CMD 적용
│   │       └── requirements.txt
│   ├── Oliview_chatbot_a/          # 올리챗 (Streamlit)
│   │   ├── Dockerfile              # baseUrlPath=bteam/chata 적용
│   │   ├── config.json             # 192.168.x.x 제거 -> vllm-serv-gateway
│   │   └── llm_common.py           # Multi-tier 2B/4B 라우팅 및 4096 토큰 확장
│   └── Oliview_chatbot_b/          # 올원챗 (FastAPI)
│       └── project_ragapi.py       # root_path=/bteam/chatb 및 Multi-tier 4B 합성 라우팅
└── ateam/                          # [MODIFY] A-Team 서브시스템
    ├── docker-compose.yml          # DB 포트 격리, aiservice-network 통합
    └── pilos-sentiment-index/
        ├── Dockerfile              # Gunicorn WSGI
        └── pilos/web/app.py        # ProxyFix 및 내부 LLM 게이트웨이 엔드포인트 일원화
```

**Structure Decision**:
최상위에 전용 `gateway/`를 신규 배치하고 루트 `docker-compose.yml`을 통해 전체 스택을 오케스트레이션하며, 기존 `ateam`, `bteam`, `model_gateway`의 비즈니스 로직을 보존하면서 네트워크 통신 계층과 환경 변수를 비파괴적으로 정합화한다.

## Complexity Tracking

> **Constitution Check All Passed** (불필요한 복잡성 위반 0건)

| Area | Why Chosen | Simpler Alternative Rejected Because |
|---|---|---|
| 전용 Nginx 게이트웨이 | 단일 포트(80) 및 5개 서브경로 분기 라우팅 | 각 컨테이너별 개별 포트 노출은 포트 충돌 및 브라우저 CORS 문제 유발 |
| 단일 Docker 네트워크 | 컨테이너 DNS 해석 및 100% 사설 보안 격리 | 다중 분리 네트워크는 컨테이너 간 DNS 해석 실패(챗봇 연결 오류) 유발 |
| Multi-tier 2B/4B 라우팅 | 속도(2B, 70 tok/s)와 심층 품질(4B) 동시 달성 | 단일 2B 모델은 리포트 품질 한계, 단일 대형 모델은 대화 지연 심화 |
