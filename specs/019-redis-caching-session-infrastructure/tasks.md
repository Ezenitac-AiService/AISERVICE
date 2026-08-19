# Tasks: Redis 기반 인메모리 캐싱·세션 인프라 및 DBMS 최적화 (Spec 019)

**Input**: Design documents from `specs/019-redis-caching-session-infrastructure/`  
**Prerequisites**: `spec.md`, `plan.md`, `data-model.md`, `contracts/`, `research.md`, `quickstart.md`

---

## Phase 1: Setup & Infrastructure (Shared Infrastructure)

**Purpose**: Redis 컨테이너 배치 및 서브프로젝트 의존성 환경 구성

- [X] T001 Add `redis:7-alpine` service to `docker-compose.yml` with port 6379, maxmemory 256mb, and `aiservice-network`
- [X] T002 [P] Add `redis>=5.0.0` dependency to `model_gateway/requirements.txt`, `bteam/requirements.txt`, and `ateam/pilos-sentiment-index/pyproject.toml`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Redis 매니저 공통 어댑터, 커넥션 풀링 및 장애 격리(Circuit Breaker) 회로 구축

- [X] T003 [P] Create unit tests for Redis connection pooling and graceful fallback in `model_gateway/tests/unit/test_redis_manager.py`
- [X] T004 Implement `BaseRedisManager` and `RedisManager` with automatic fallback in `model_gateway/src/core/redis_manager.py`
- [X] T005 [P] Implement `GET /health/redis` endpoint in `model_gateway/src/api/routes/health_api.py`

**Checkpoint**: Foundation ready — Redis 클라이언트 및 헬스체크가 준비되어 사용자 스토리 구현 착수 가능.

---

## Phase 3: User Story 1 - RAG 질의 임베딩 및 리랭킹 인메모리 캐싱 (Priority: P1) 🎯 MVP

**Goal**: BGE-M3 임베딩 및 BGE-Reranker 점수를 Redis에 캐싱하여 반복 질의 지연 시간을 100ms → 0.5ms로 단축.

**Independent Test**: 동일한 RAG 질의 2회 호출 시 2번째 질의의 임베딩/리랭킹 단계 지연 시간이 1ms 미만으로 측정되는지 검증.

### Tests for User Story 1 (TDD)
- [X] T006 [P] [US1] Create unit tests for embedding and rerank caching in `model_gateway/tests/unit/test_rag_cache.py`

### Implementation for User Story 1
- [X] T007 [US1] Integrate Redis embedding vector caching (`emb:{model}:{sha256}`) in `model_gateway/src/api/routes/inference_api.py` and `bteam/oliview_core/retrieval.py`
- [X] T008 [US1] Integrate Redis reranker score caching (`rerank:{query_hash}:{doc_ids_hash}`) in `model_gateway/src/api/routes/inference_api.py` and `bteam/oliview_core/rerank.py`

**Checkpoint**: User Story 1 (MVP) is fully functional and testable independently.

---

## Phase 4: User Story 2 - 분산 세션 관리 및 멀티턴 대화 히스토리 영속화 (Priority: P1)

**Goal**: ChatA(Streamlit), ChatB(FastAPI), PILOS Web의 멀티턴 대화 세션을 Redis에 3일간 영속 보존하여 새로고침/재시작 후 맥락 100% 복원.

**Independent Test**: 대화 진행 후 브라우저 새로고침(F5) 시 이전 대화 맥락이 즉시 복원되는지 검증.

### Tests for User Story 2 (TDD)
- [X] T009 [P] [US2] Create unit tests for multi-turn session persistence in `bteam/tests/unit/test_session_store.py`

### Implementation for User Story 2
- [X] T010 [US2] Implement `RedisSessionStore` with sliding window TTL in `bteam/oliview_core/session.py`
- [X] T011 [US2] Integrate `RedisSessionStore` into `bteam/Oliview_chatbot_a/app.py` and `bteam/Oliview_chatbot_b/project_ragapi.py`

**Checkpoint**: User Stories 1 AND 2 are fully functional and integrated.

---

## Phase 5: User Story 3 - PILOS 비동기 감정 분석 분산 작업 큐 및 잠금 (Priority: P2)

**Goal**: MySQL 폴링을 Redis 인메모리 큐(`queue:pilos:jobs`) 및 분산 락(`lock:pilos:{id}`)으로 전환하여 DB I/O 95% 절감.

**Independent Test**: 100건의 리뷰 분석 요청을 동시 인큐 시 누락 및 중복 없이 워커에서 분산 처리되는지 검증.

### Tests for User Story 3 (TDD)
- [X] T012 [P] [US3] Create unit tests for Redis async queue and distributed lock in `ateam/pilos-sentiment-index/tests/test_redis_queue.py`

### Implementation for User Story 3
- [X] T013 [US3] Implement `RedisJobQueue` and `RedisLock` in `ateam/pilos-sentiment-index/pilos/core/redis_queue.py`
- [X] T014 [US3] Refactor PILOS Web (`pilos/web/app.py`) and Worker (`pilos/worker.py`) to process jobs via Redis queue

**Checkpoint**: User Stories 1, 2, 3 are fully functional across the pipeline.

---

## Phase 6: User Story 4 & 5 - Rate Limiting & DBMS 최적화 (Priority: P2/P3)

**Goal**: Redis Lua 토큰 버킷 Rate Limiter 구축 및 MySQL 복합 인덱스·ChromaDB HNSW 파라미터 튜닝으로 캐시 미스 시 20ms 방어.

**Independent Test**: 초당 30회 요청 시 429 에러 반환 검증; 캐시 미스 시 MySQL 리뷰 쿼리 실행 시간 < 20ms 검증.

### Implementation for User Story 4 & 5
- [X] T015 [P] [US4] Implement Token Bucket Rate Limiter via Lua Script in `model_gateway/src/core/redis_manager.py`
- [X] T016 [P] [US5] Execute MySQL composite index migrations (`idx_product_review_date`, `idx_brand_rating`) in `bteam_db` and `pilos-db`
- [X] T017 [P] [US5] Optimize ChromaDB `hnsw:search_ef = 64` and SQLAlchemy connection pool parameters in `bteam/oliview_core/config.py`

**Checkpoint**: All 5 User Stories are fully functional across the system.

---

## Phase 7: Polish & Cross-Cutting Verification

**Goal**: 전체 파이프라인 통합 테스트 및 벤치마크 검증 완료.

- [X] T018 [P] Run full unit and integration test suite across all subprojects
- [X] T019 Execute quickstart benchmark scenarios in `quickstart.md` (Cache hit < 1ms, MySQL query < 20ms)
- [X] T020 Rebuild containers with `docker compose build` and verify live services (`vllm-serv`, `redis`, `oliview_chatbot_a`, `oliview_chatbot_b`, `pilos_web`, `aiservice-gateway`)

**Checkpoint**: 100% of Spec 019 tasks implemented and verified live.

---

## Dependencies & Execution Order

### Phase Dependencies
- **Phase 1 (Setup)**: Can start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1 (BLOCKS all User Stories).
- **Phase 3 (User Story 1 - MVP)**: Depends on Phase 2.
- **Phase 4 (User Story 2)**: Depends on Phase 2.
- **Phase 5 (User Story 3)**: Depends on Phase 2.
- **Phase 6 (User Story 4 & 5)**: Depends on Phase 2.
- **Phase 7 (Polish)**: Depends on all User Stories completion.
