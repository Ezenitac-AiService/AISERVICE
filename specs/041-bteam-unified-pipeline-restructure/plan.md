# Implementation Plan: Oliview B-Team 전주기 데이터 및 서비스 파이프라인 통합 재구성

**Branch**: `041-bteam-unified-pipeline-restructure` | **Date**: 2026-08-26 | **Spec**: [spec.md](./spec.md)  
**Constitution Version**: v1.1.1 Compliant  

---

## Summary

본 피처는 분산 격리되어 있던 B팀의 6개 하위 프로젝트(`Oliview_Project`, `Oliview_aspect_sentence_split`, `Oliview_aspect_sentiment`, `Oliview_LLM`, `Oliview_chatbot_a`, `Oliview_chatbot_b`)를 표준 3계층 모노레포 구조(`packages/core`, `models/`, `pipelines/`, `services/`)로 물리적 통합 재구성합니다. 또한 "크롤링 $\rightarrow$ 문장 분리 $\rightarrow$ 감성 분석 $\rightarrow$ LLM 보고서 생성 $\rightarrow$ ChromaDB 증분 벡터 인덱싱"을 원클릭으로 구동하는 `pipelines/pipeline_runner.py`를 구축하고, 500 청크 커밋, SQLite 락 방어, GPU 스로틀링, PII 마스킹, Redis 캐시 자동 무효화, 도커 빌드 격리 및 Nginx 무중단 동기화를 완전 구현합니다.

---

## Technical Context

- **Language/Version**: Python 3.12 (uv workspace), Node.js 20 (React 19 Vite)
- **Primary Dependencies**: PyMySQL, SQLAlchemy, ChromaDB, FastAPI, Streamlit, Flask, PyTorch, Transformers, httpx, Redis
- **Storage**: MySQL 8.0 (`cosmetic_db`), ChromaDB (`chroma_db_oliview`), Redis 7.x
- **Testing**: pytest (단위/계약/통합 테스트)
- **Target Platform**: Docker Compose on Linux/Windows, Nginx Gateway
- **Project Type**: Monorepo Data Pipeline & Multi-Service Serving Platform
- **Performance Goals**: 500청크 커밋, 챗봇 P95 SLA < 5s 유지, 도커 빌드 컨텍스트 0MB 모델 전송
- **Constraints**: 헌법 v1.1.1 (100% 무환각 RAG 불변 원칙, 환경 분리, 제로 하드코딩)

---

## Constitution Check (v1.1.1)

- [X] **Principle I: 100% 무환각 RAG 불변 원칙** - 전 파이프라인 및 챗봇 서비스에서 인라인 인용 및 무환각 새니타이저 보존.
- [X] **Principle II: 엄격한 종단간 지연시간 및 하드웨어 적응형 SLA** - GPU 큐 Throttling(`max_concurrency=1~2`)을 적용하여 챗봇 실시간 SLA 5초 이내 유지.
- [X] **Principle III: 레이어별 캐싱 및 서비스 격리 보장** - 파이프라인 갱신 시 Redis L1~L5 캐시 자동 무효화 패턴 적용.
- [X] **Principle IV: 테스트 주도 및 근거 기반 검증 (Zero Mocking in Target Logic)** - TDD 기반 통합 파이프라인 및 서비스 리그레션 검증 스위트 구축.
- [X] **Principle V: 한국어 뷰티 도메인 특화 정확성** - 6대 화장품 속성 및 감성 라벨링 일관성 보장.
- [X] **Principle VI: 다중 런타임 환경 분리 및 무하드코딩 원칙** - Docker Compose 환경변수 및 Nginx 동적 DNS 리졸버 완전 연동.

---

## Project Structure & Target Files

```text
bteam/
├── packages/
│   └── core/
│       ├── pyproject.toml
│       └── oliview_core/
│           ├── __init__.py
│           ├── db/
│           │   ├── __init__.py
│           │   ├── connection.py        # [NEW] Connection Pool, Chunk Commit & Migration
│           │   └── models.py            # [NEW] SQLAlchemy ORM Models
│           ├── gateway/
│           │   ├── __init__.py
│           │   └── client.py            # [NEW] LLM, Embedding, Reranker Client with Throttling
│           ├── cache/
│           │   ├── __init__.py
│           │   └── redis_manager.py     # [NEW] Redis Cache & Auto Invalidation
│           └── guardrails/
│               ├── __init__.py
│               ├── sanitizer.py         # [NEW] Groundedness & Hallucination Sanitizer
│               └── pii_filter.py        # [NEW] PII Regex Masking
├── models/                              # [MOVED] ML Model Weights (.dockerignore)
│   ├── sentence_split/
│   └── sentiment/
├── pipelines/
│   ├── __init__.py
│   ├── crawler/                         # [MOVED/NEW] Master Product Upsert & Review Crawler
│   │   ├── __init__.py
│   │   └── crawler_runner.py
│   ├── sentence_split/                  # [MOVED/NEW] KoBERT Sentence Splitter with PII Masking
│   │   ├── __init__.py
│   │   └── split_runner.py
│   ├── sentiment/                       # [MOVED/NEW] Aspect Sentiment Classifier
│   │   ├── __init__.py
│   │   └── sentiment_runner.py
│   ├── report_generator/                # [MOVED/NEW] LLM Executive Report Generator
│   │   ├── __init__.py
│   │   └── report_runner.py
│   ├── vector_indexer/                  # [NEW] MySQL -> ChromaDB Incremental Indexer with Lock Defense
│   │   ├── __init__.py
│   │   └── indexer_runner.py
│   └── pipeline_runner.py               # [NEW] E2E CLI Orchestrator
├── services/
│   ├── dashboard_backend/               # [MOVED] Flask REST API
│   │   ├── Dockerfile
│   │   └── app.py
│   ├── dashboard_frontend/              # [MOVED] React 19 Vite Dashboard
│   │   ├── Dockerfile
│   │   └── src/
│   ├── chatbot_a/                       # [MOVED] Streamlit RAG Chatbot
│   │   ├── Dockerfile
│   │   └── app.py
│   └── chatbot_b/                       # [MOVED] FastAPI Hybrid RAG Chatbot
│       ├── Dockerfile
│       └── main.py
├── docker-compose.yml                   # [MODIFY] Standardized Service Topology
├── .dockerignore                        # [NEW] 2GB Models & Artifacts Build Isolation
├── pyproject.toml                       # [NEW] Root UV Workspace Configuration
└── tests/
    ├── test_e2e_pipeline.py             # [NEW] E2E Pipeline Orchestrator Tests
    ├── test_feature_040_mobile_layout.py
    └── test_feature_039_zero_search.py
```

---

## 5-Stage Atomic Implementation Roadmap

### Phase 1: Core Package & Foundation (`packages/core`)
- `packages/core/oliview_core` 구축: DB Connection Pool, PII Filter, Gateway Client, Redis Manager.
- 루트 `pyproject.toml` UV 워크스페이스 구성.

### Phase 2: ML Model Weights & Pipeline Modules Migration (`models/`, `pipelines/`)
- 가중치 `models/sentence_split`, `models/sentiment`로 물리 이동.
- 크롤러, 문장분리, 감성분석, 보고서생성, 벡터인덱서 모듈 `pipelines/`로 표준화 및 리팩토링.
- `pipelines/pipeline_runner.py` E2E 오케스트레이터 구현.

### Phase 3: Services Reorganization & Import Alignment (`services/`)
- `services/dashboard_backend`, `services/dashboard_frontend`, `services/chatbot_a`, `services/chatbot_b`로 물리 이동.
- 모든 서비스의 `common.py` 중복 제거 및 `oliview_core` 패키지 단일 임포트 전환.

### Phase 4: Docker Compose & Gateway Nginx Synchronization
- `bteam/docker-compose.yml` 컨테이너명 및 볼륨 마운트 갱신 (`bteam_db`, `bteam_dashboard_backend`, `bteam_dashboard_frontend`, `bteam_chatbot_a`, `bteam_chatbot_b`).
- 루트 `.dockerignore` 2GB 모델 격리 적용.
- `gateway/nginx.conf` 프록시 업스트림 서비스명 동기화 및 Nginx 리로드.

### Phase 5: End-to-End Verification & Legacy Purge
- `pipeline_runner.py --steps all` 실행 검증.
- `pytest` 전수 리그레션 테스트 100% 통과.
- 레거시 잔여 폴더 완전 삭제 및 라이브 브라우저 검증.
