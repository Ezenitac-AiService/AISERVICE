# Implementation Plan: Redis 기반 인메모리 캐싱·세션 인프라 및 DBMS 최적화 (Spec 019)

**Branch**: `019-redis-caching-session-infrastructure` | **Date**: 2026-08-19 | **Spec**: [spec.md](./spec.md)

---

## 1. Summary

NVIDIA GeForce GTX 1070 (8GB VRAM) 환경에서 GPU VRAM 0MB 증가 원칙을 유지하며, `redis:7-alpine` 독립 컨테이너를 도입하여 **① RAG 임베딩/리랭킹 3단계 계층 캐시**, **② ChatA/ChatB/PILOS 멀티턴 세션 영속화**, **③ PILOS 비동기 작업 큐 및 분산 락**, **④ 토큰 버킷 Rate Limiter**, **⑤ MySQL 복합 인덱스 및 ChromaDB 벡터 튜닝**을 통합 구축합니다.

---

## 2. Technical Context

- **Language/Version**: Python 3.12 (A-Team, B-Team, Model Gateway), SQL (MySQL 8.0), Shell
- **Primary Dependencies**: `redis>=5.0.0`, `fastapi`, `streamlit`, `httpx`, `sqlalchemy`, `chromadb`, `pydantic>=2.0`
- **Storage/Infrastructure**:
  - `redis:7-alpine` Docker 컨테이너 (`maxmemory 256mb`, `allkeys-lru`, RDB 스냅샷)
  - `bteam_db` & `pilos-db` (MySQL 8.0 - InnoDB)
  - `ChromaDB` (HNSW Local Vector Store)
- **Testing**: `pytest`, `unittest`, Asyncio Test Suite
- **Target Platform**: Docker Compose / Linux Container (WSL2 Ubuntu 24.04 on Windows)
- **Project Type**: Microservices Backend, In-Memory Caching, Distributed Queue & DB Optimization
- **Performance Goals**:
  - Embedding / Rerank Cache Hit 지연: **< 1.0ms**
  - Session History 조회: **< 2.0ms**
  - MySQL Cache Miss 쿼리 지연: **< 20.0ms**
  - ChromaDB 벡터 검색 속도: **30% 이상 향상**
- **Constraints**: GPU VRAM 0MB 추가 점유, Host RAM < 100MB, Redis 장애 시 Zero-Downtime Graceful Fallback

---

## 3. Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 원칙 (Constitution Principle) | 준수 현황 | 검증 세부 내용 |
| :--- | :---: | :--- |
| **I. 언어 및 커뮤니케이션 (Korean)** | **PASS** ✅ | 모든 산출물(`plan.md`, `data-model.md`, `research.md`, `contracts/`, `quickstart.md`) 한국어 작성 완료. |
| **II. TDD 및 계약 검증 (Test-First)** | **PASS** ✅ | `test_redis_cache.py`, `test_session_store.py`, `test_db_indexes.py` 선행 테스트 작성 및 검증. |
| **III. 서비스 모듈화 및 격리** | **PASS** ✅ | Redis를 `aiservice-network` 독립 컨테이너로 격리 배포하며 기존 코드베이스 비파괴적 확장. |
| **IV. 관측 가능성 및 로깅** | **PASS** ✅ | `GET /health/redis` 및 Prometheus 캐시 적중률(Hit Rate) 메트릭 연동. |
| **V. 단순성 및 점진적 진화 (YAGNI)** | **PASS** ✅ | 복잡한 외부 분산 프레임워크 대신 가볍고 검증된 `redis-py` 표준 클라이언트 채택. |

---

## 4. Project Structure & Artifacts

### 4.1 Documentation (this feature)
```text
specs/019-redis-caching-session-infrastructure/
├── spec.md              # Feature Specification (Clarifications included)
├── plan.md              # Implementation Plan (This file)
├── research.md          # Technical Research & 2026 Multi-Layer Caching Decisions
├── data-model.md        # Redis Key Schema & MySQL Composite Index Models
├── contracts/           # BaseRedisManager & Observability Endpoints Contract
│   └── redis_service_contracts.md
├── quickstart.md        # Quickstart Benchmark & Verification Guide
├── checklists/          # Requirements Quality Checklist (16/16 PASS)
│   └── requirements.md
└── tasks.md             # Task Breakdown (/speckit-tasks output)
```

### 4.2 Source Code Layout
```text
model_gateway/
├── src/
│   ├── core/
│   │   ├── redis_manager.py          # [NEW] Redis Cache & Rate Limiter Manager
│   │   └── base_engine.py
│   └── api/routes/
│       ├── health_api.py             # [MODIFY] /health/redis 엔드포인트 연동
│       └── inference_api.py          # [MODIFY] Embedding/Rerank/LLM Cache 연동
bteam/
├── oliview_core/
│   ├── client.py                     # [MODIFY] Redis Cache Layer 통합
│   └── session.py                    # [NEW] Redis Distributed Chat Session Store
├── Oliview_chatbot_a/
│   └── app.py                        # [MODIFY] Redis Session History 연동
└── Oliview_chatbot_b/
    └── project_ragapi.py             # [MODIFY] Redis Session History 연동
ateam/pilos-sentiment-index/
├── pilos/
│   ├── core/
│   │   └── redis_queue.py            # [NEW] Redis Async Job Queue & Lock
│   ├── service/
│   │   └── rag_service.py            # [MODIFY] Redis Caching 연동
│   └── web/
│       └── app.py                    # [MODIFY] Redis Job Enqueue 연동
docker-compose.yml                    # [MODIFY] Redis 7.4 Alpine 서비스 추가
```

---

## 5. Implementation Phases Overview

- **Phase 1: Setup & Infrastructure**
  - `docker-compose.yml`에 `redis` 서비스 및 헬스체크 추가.
  - 서브프로젝트 의존성(`redis>=5.0.0`) 설정.
- **Phase 2: Foundational Components (TDD)**
  - `BaseRedisManager` 및 `RedisManager` 클라이언트 구현 (연결 풀, Graceful Fallback 회로).
  - 단위 테스트 스위트(`tests/unit/test_redis_manager.py`) 구축.
- **Phase 3: User Story 1 (RAG Multi-Layer Caching)**
  - `model_gateway` 및 `oliview_core`에 BGE-M3 임베딩, BGE-Reranker 캐시 연동.
- **Phase 4: User Story 2 & 3 (Session Persistence & PILOS Async Queue)**
  - ChatA, ChatB, PILOS 대화 세션 Redis 연동.
  - PILOS 워커를 Redis `queue:pilos:jobs` 비동기 큐로 전환.
- **Phase 5: User Story 4 & 5 (Rate Limiting & DBMS Co-Optimization)**
  - Lua 스크립트 기반 토큰 버킷 Rate Limiter 구축.
  - MySQL `(product_id, review_date)` 복합 인덱스 마이그레이션 및 ChromaDB `ef_search` 튜닝.
- **Phase 6: Polish & Live Verification**
  - 도커 컨테이너 기동, 벤치마크 검증(지연 시간 < 1ms), E2E 테스트.
