# Implementation Plan: Oliview B-Team 전주기 데이터 및 서비스 파이프라인 통합 재구성

**Branch**: `041-bteam-unified-pipeline-restructure` | **Date**: 2026-08-27 | **Spec**: [spec.md](./spec.md)
**Constitution Version**: v1.1.1 | **Compliance**: quality-gate validation required

---

## Summary

본 피처는 분산되어 있던 B팀의 6개 하위 프로젝트와 기존 `bteam/oliview_core`를 inventory 기반으로 보존·검증하면서, Blue 원본을 제자리에 둔 Green 복제본을 하나의 monorepo/uv workspace 안의 `packages/core`, `models/`, `pipelines/`, `services/` 4개 논리 계층으로 통합 재구성합니다. 이는 단일 컨테이너화가 아니다. `pipeline_runner`, Dashboard backend/frontend, ChatA, ChatB는 독립 컨테이너로 유지하고 MySQL·Redis·ChromaDB persistence·Model Gateway도 별도 의존 서비스로 격리합니다. 기존 운영 스택은 Blue로 계속 서비스하고 새 Green 멀티 컨테이너 스택을 별도 Compose project로 구축하여 계약·E2E·복구·보안·성능·readiness를 모두 통과한 뒤에만 외부 변경 권한자가 승인한 Nginx cutover를 수행합니다. cutover 후에도 Blue를 최소 24시간 유지하며 rollback rehearsal과 별도 decommission 승인을 완료하기 전에는 원본을 이동·중지·삭제하지 않습니다.

---

## Technical Context

- **Language/Version**: Python 3.12 (uv workspace), Node.js `^20.19.0 || >=22.12.0` (React 19, Vite 8 lockfile)
- **Primary Dependencies**: PyMySQL, SQLAlchemy, Alembic, ChromaDB, FastAPI, Streamlit, Flask, PyTorch, Transformers, httpx, Redis, pydantic-settings
- **Storage**: MySQL 8.0 (`cosmetic_db`), ChromaDB (`chroma_db_oliview`), Redis 7.x
- **Testing**: pytest (단위/계약/통합/성능/보안), ruff, mypy, `npm ci`/ESLint/Vite production build, Docker Compose contract test
- **Target Platform**: Docker Compose on Linux/Windows, 별도 project/network의 Blue-Green 멀티 컨테이너, Nginx Gateway
- **Project Type**: Monorepo Data Pipeline & Multi-Service Serving Platform
- **Performance Goals**: `batch_size=500`, spec의 Performance Baseline Matrix 기준 DEMO/PRODUCTION별 SLA, Docker build context에 모델·SQL dump·ChromaDB·가상환경 0바이트 포함
- **Constraints**: 헌법 v1.1.1 (TDD, 비파괴적 보존, 구조화 로그, 서비스·환경 격리, 무하드코딩, 무환각·인용 무결성), Green 전체 검증 전 Blue 변경 금지, 승인 전환 후 최소 24시간 rollback 가능 상태 유지

---

## Constitution Check (v1.1.1)

- [ ] **Principle I: 언어 및 커뮤니케이션 정책** - 사용자 대상 문서와 작업 목록을 한국어로 유지하고 기술 용어만 원어 병기.
- [ ] **Principle II: TDD 및 계약 검증** - 구현 전에 DB/Gateway/서비스 계약 테스트를 작성하고 기대한 Red를 확인하며, 각 구현 단계 뒤 해당 범위를 Green으로 전환.
- [ ] **Principle III: 모듈화·격리·비파괴 보존** - 애플리케이션별 독립 컨테이너 경계를 유지하고 기존 Blue 컨테이너·네트워크·볼륨·모델·DB·설정을 manifest와 복구 테스트로 보존.
- [ ] **Principle IV: 관측 가능성·구조화 로깅** - `run_id`, 단계, latency, 오류를 기록하고 API key·토큰·PII를 마스킹.
- [ ] **Principle V: 단순성·점진적 진화** - 호환 계층과 단계별 migration으로 범위를 분리하고 불필요한 재작성 금지.
- [ ] **Principle VI: 동적 운영 모드·무환각** - 공통 `Settings` schema와 서비스별 환경·secret allowlist를 사용하고, PRODUCTION의 서로 다른 GPU instance 기반 Gateway 2개 이상과 Redis Sentinel quorum 또는 managed HA 전제, Performance Baseline Matrix, 검색 0건 abstention, 인라인 citation 무결성을 검증.
- [ ] **Quality Gates** - pytest, contract, performance, security, Python lint/type-check, frontend locked install/lint/build를 모두 실행하고 결과를 보존.

---

## Project Structure & Target Files

```text
bteam/
├── packages/
│   └── core/
│       ├── pyproject.toml
│       ├── alembic/
│       │   └── versions/               # [NEW] Additive, Blue-compatible migrations
│       └── oliview_core/
│           ├── __init__.py
│           ├── db/
│           │   ├── __init__.py
│           │   ├── connection.py        # [NEW] Connection Pool, Chunk Commit & Migration
│           │   └── models.py            # [NEW] SQLAlchemy ORM Models
│           ├── config.py                 # [NEW] Pydantic Settings / APP_RUN_MODE
│           ├── logging.py                # [NEW] Structured Logging & Redaction
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
├── models/                              # [GREEN COPY] checksum-verified ML weights (.dockerignore)
│   ├── sentence_split/
│   ├── sentiment/
│   └── embeddings/                       # [GREEN COPY/OPTIONAL] Local fallback weights
├── pipelines/
│   ├── pyproject.toml                   # uv workspace member
│   ├── __init__.py
│   ├── Dockerfile                      # [NEW] Independent pipeline_runner image
│   ├── crawler/                         # [GREEN COPY/NEW] Master Product Upsert & Review Crawler
│   │   ├── __init__.py
│   │   └── crawler_runner.py
│   ├── sentence_split/                  # [GREEN COPY/NEW] KoBERT Sentence Splitter with PII Masking
│   │   ├── __init__.py
│   │   └── split_runner.py
│   ├── sentiment/                       # [GREEN COPY/NEW] Aspect Sentiment Classifier
│   │   ├── __init__.py
│   │   └── sentiment_runner.py
│   ├── report_generator/                # [GREEN COPY/NEW] LLM Executive Report Generator
│   │   ├── __init__.py
│   │   └── report_runner.py
│   ├── vector_indexer/                  # [NEW] MySQL -> ChromaDB Incremental Indexer with Lock Defense
│   │   ├── __init__.py
│   │   └── indexer_runner.py
│   └── pipeline_runner.py               # [NEW] E2E CLI Orchestrator
├── services/
│   ├── dashboard_backend/               # [GREEN COPY] Flask REST API
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   └── app.py
│   ├── dashboard_frontend/              # [GREEN COPY] React 19 Vite Dashboard
│   │   ├── package.json
│   │   ├── package-lock.json
│   │   ├── Dockerfile
│   │   └── src/
│   ├── chatbot_a/                       # [GREEN COPY] Streamlit RAG Chatbot
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   └── app.py
│   └── chatbot_b/                       # [GREEN COPY] FastAPI Hybrid RAG Chatbot
│       ├── pyproject.toml
│       ├── Dockerfile
│       └── main.py
├── migration/                            # [NEW] Inventory, checksum, snapshot, rollback artifact
├── deployment/                           # [NEW] Candidate Nginx, cutover/rollback, service env allowlists
├── contracts/
│   ├── pipeline_runner_contract.json
│   ├── product_report_schema.json
│   └── deployment_gate_contract.json     # [NEW] Auditable transition gates
├── docker-compose.yml                   # [KEEP] Existing Blue topology; Green 검증 중 변경 금지
├── docker-compose.green.yml             # [NEW] Parallel Green multi-container topology
├── docker-compose.production.yml        # [NEW] 2+ distinct-GPU Gateway endpoints and Redis HA override
├── .dockerignore                        # [NEW] 2GB Models & Artifacts Build Isolation
├── alembic.ini                          # [NEW] Versioned migration configuration
├── pyproject.toml                       # [NEW] Exact five-member UV workspace
├── uv.lock                              # [NEW] Shared Python lockfile
└── tests/
    ├── characterization/                # [NEW] Existing behavior baseline
    ├── unit/                             # [NEW] Core and pipeline unit tests
    ├── contract/                         # [NEW] DB/Gateway/HTTP/Compose/Blue-Green contracts
    ├── integration/                      # [NEW] Service and E2E tests
    ├── performance/                      # [NEW] P95 and lock contention tests
    ├── security/                         # [NEW] PII/secret leakage tests
    ├── fixtures/                          # [NEW] PII, zero-search, citation, performance fixtures
    │   ├── pii_corpus.jsonl
    │   ├── zero_search_corpus.jsonl
    │   ├── citation_fixture.json
    │   └── performance_queries.jsonl
    └── test_e2e_pipeline.py              # [NEW] E2E Pipeline Orchestrator Tests
```

## Data Model & Contract Decisions

- 논리 `ReviewSentence`와 `SentimentAnalysis`는 각각 기존 `review_aspect_sentences`, `aspect_sentiment_results`에 매핑한다. 새 generic sentence/sentiment 테이블을 만들지 않는다.
- 상품의 브랜드·카테고리는 `products.brand_id`, `product_categories`, `categories` 조인으로 제공하며, 보고서 API의 `brand_name/category`는 read projection이다.
- schema v2의 DB/HTTP projection은 보존된 속성 보고서 행을 `attributes[]`로, 상품 전체 감성 집계를 `statistics`로, 속성별 감성 집계를 `aspect_summary`로 반환한다. `attributes[]`는 `attribute_report_id`, `analysis_category_id`, `display_name`, `positive_summary`, `negative_summary`, `generated_at`을 가지며 report의 `product_id`와 일치하는 행만 포함한다. `statistics`는 `total_sentence_count`, 긍정·부정·중립 count와 0~100 범위의 `positive_ratio`/`negative_ratio`를 포함한다.
- 보고서 API는 보존된 보고서 테이블, additive `llm_product_report_claims`/`llm_product_report_citations`와 통계 집계를 조합한다. 보고서·claim·citation은 한 트랜잭션으로 저장하고 citation의 리뷰 존재·동일 product 소속·PII 처리 quote substring을 검증한다. 기존 citation 없는 행은 `abstained/LEGACY_UNVERIFIED`이며 추측으로 grounded 승격하지 않는다. `report_id := llm_product_report_id`, `created_at := generated_at(UTC)`, `positive_ratio`는 0~100 퍼센트로 고정한다.
- Dashboard backend는 `/bteam/oliview/api/search` POST를 ChatA/ChatB와 동일한 Core hybrid retrieval·source review grounding 경로에 연결한다. 요청은 query와 선택적 `product_id`·query embedding을 받고, 응답은 `source_review_id` citation 또는 정의된 abstention만 반환한다. 이 경로는 pipeline v2 index freshness probe의 Dashboard leg로 사용하며 Green에서만 검증한다.
- `PipelineRunHistory`는 `(run_id, step_name, scope_key)` unique constraint와 checkpoint payload를 가진다. 별도 `PipelineActiveLease`가 `(step_name, scope_key)`를 전역 유일하게 관리한다. 전체 cycle은 `(cycle, all)` coordinator lease를, 단일/전체 실행의 실제 제품 작업은 선택 단계 전체 동안 `(product_pipeline, product:{product_id})` lease를 사용한다. owner token, 15초 heartbeat, 60초 TTL을 기록하고 MySQL server UTC를 기준으로 만료를 판단한다. 만료 lease 회수와 이전 이력의 `FAILED/LEASE_EXPIRED` 전환은 한 트랜잭션에서 수행한다.
- `pipeline_runner.py`는 `--interval-hours=0` 단일 전체/제품 실행, 양수 foreground 주기 실행을 담당한다. Resume은 정확한 `--resume-run-id`와 원래 selector·steps 일치가 필요하다. 주기 cycle은 immutable watermark를 사용하고, crawl은 due 조건을, 후속 단계는 단계별 성공 checkpoint 이후의 변경 입력을 선택하며 전체 cycle 성공 후에만 watermark를 전진시킨다.
- `APP_RUN_MODE=DEMO|PRODUCTION`은 성능·운영 정책을, `DEPLOYMENT_STAGE=VALIDATION|CUTOVER`는 data-plane 접근 정책을 제어한다. VALIDATION은 격리 write endpoint만 허용한다. CUTOVER 진입·첫 migration write·Nginx 전환·Blue 폐기는 `deployment_gate_contract.json`의 `CUTOVER_APPROVED`·`BACKUP_READY`·`DATA_MIGRATION_READY`·`DECOMMISSION_APPROVED`를 순서대로 요구한다.
- ChromaDB는 기존 `oliview_review_sentences` v1을 Green VALIDATION에서 read-only로 보존하고 canonical `oliview_review_sentences_v2`에 `id=str(aspect_sentence_id)`, 동일한 `source_review_id`/`review_id` metadata를 저장한다. 승인된 cutover/soak만 v1 exact-shape dual-write를 허용하며 collection별 lag를 기록한다.
- Redis key는 Green에서 `bteam:{APP_RUN_MODE}:product:{product_id}:{report|rag}:v{version}` namespace를 사용한다. 성공 범위만 version을 전진시킨다. legacy key는 product-addressable class만 exact-key 무효화하고 hash 기반 class는 scan/delete하지 않은 채 rollback cache-bypass/격리 Redis profile로 처리한다. `FLUSHDB`, wildcard 삭제, production `KEYS`/전역 `SCAN`을 금지한다.
- 루트 uv workspace member는 `packages/core`, `pipelines`, `services/dashboard_backend`, `services/chatbot_a`, `services/chatbot_b`로 고정한다. Frontend는 uv에서 제외하고 Vite 8 lockfile과 Node `^20.19.0 || >=22.12.0`로 검증한다.

## Deployment & Migration Model

| Boundary | Blue | Green | Invariant |
| :--- | :--- | :--- | :--- |
| Application containers | 현재 Dashboard backend/frontend, ChatA, ChatB 및 관련 runner | 동일 책임의 독립 컨테이너 | 한 프로세스·한 컨테이너로 병합하지 않는다. |
| Compose/network | 현재 project·network·alias·host port | `bteam-green` project, color별 alias, 내부/`127.0.0.1` candidate port | Green 구축·검증 중 Blue 이름·network·volume·host port를 변경하거나 재사용하지 않는다. |
| Data dependencies | 기존 운영 MySQL/Redis/ChromaDB/Model Gateway | VALIDATION: 복구 snapshot·격리 Redis / CUTOVER: 승인된 backward-compatible 운영 endpoint | VALIDATION 중 Blue data plane 쓰기를 금지하고 CUTOVER 승인 뒤에만 fresh backup·호환 migration·delta sync를 수행한다. |
| Public traffic | 기존 Nginx active upstream | candidate route만 사용 | 전체 품질 gate와 cutover 승인 전 외부 upstream을 바꾸지 않는다. |

전환 순서는 다음과 같이 고정한다.

1. 실행 중인 Blue 컨테이너·network·volume·Nginx upstream을 inventory하고 외부 endpoint 기준선을 기록한다.
2. MySQL/ChromaDB snapshot을 복구하고 격리 Redis를 구성한 뒤 `docker-compose.green.yml`을 `bteam-green` project로 기동하여 Blue와 병행한다. preflight는 Green write endpoint가 Blue 운영 endpoint와 다름을 검증한다.
3. Green candidate route에서 Red→Green 계약, E2E, 복구, 보안, 성능, readiness 및 rollback rehearsal을 완료한다.
4. 외부 변경 권한자가 발급한 cutover 승인을 검증한 뒤 Blue 사용자 HTTP 서비스는 유지한 채 background writer를 drain하고 fresh backup, Blue 호환 additive migration과 checkpoint 기반 final delta sync를 수행한다. MySQL delta, Chroma v1/v2 lag가 모두 0이고 legacy Redis key class마다 exact-target 또는 bypass/isolated 증거가 있어야만 `DATA_MIGRATION_READY`를 기록한다. 구현 자동화는 승인 artifact를 생성하지 않으며, gate가 없으면 운영 쓰기와 `nginx` reload 전에 종료한다.
5. 최소 24시간 soak 동안 Blue를 실행 상태로 유지하고 spec의 Cutover & Rollback Thresholds를 감시하며 초과 시 즉시 Blue로 rollback한다.
6. soak와 rollback 검증 후 외부 변경 권한자가 발급한 별도 decommission 승인을 검증해야만 Blue를 중지하고 기존 원본을 recoverable archive로 이동한다. 운영 volume과 snapshot은 기본적으로 삭제하지 않는다.

---

## 단계별 구현 로드맵

### Phase 0: Baseline, Inventory & Recovery
- 기존 소스·모델·설정·DB dump·ChromaDB와 실행 중인 Blue 컨테이너·network·volume·Nginx upstream manifest 생성. secret 값은 제외하고 파일명·키 이름·redacted 존재 여부·hash만 기록한다. Blue는 변경하지 않고 계속 서비스한다.
- 기존 테스트를 characterization suite로 고정하고 DB/ChromaDB 복구 dry-run 수행.

### Phase 1: Contracts & Red Tests
- 기존 MySQL 스키마와 additive claim/citation 저장, 보고서 API projection, Gateway, versioned/legacy Redis class, Chroma v1/v2 metadata, 정확한 uv member와 frontend lockfile 계약을 확정.
- Core·pipeline·service·cache·보고서·Blue-Green Compose·PRODUCTION topology 계약 테스트와 고정 성능 fixture를 먼저 작성하고 실패를 확인.

### Phase 2: Core Package & Migration Layer (`packages/core`)
- DB connection pool, Alembic migration, 실제 물리 스키마 ORM compatibility mapping, `PipelineRunHistory`, `PipelineActiveLease`, 공통 `Settings` schema와 서비스별 allowlist, structured logging, guardrails, Gateway client, versioned Redis manager 구현.

### Phase 3: Models & Pipeline Modules (`models/`, `pipelines/`)
- 모델을 Green 경로로 비파괴 복제하고 원본/복제본 checksum을 검증한다. Blue 원본은 이동하지 않는다.
- 크롤러, 문장분리, 감성분석, 보고서생성, 벡터인덱서와 `pipeline_runner.py` 구현.
- 정확한 `--resume-run-id`, 단계별 eligibility/watermark, lease heartbeat/expiry, idempotency, partial failure, versioned cache invalidation, zero-search/claim citation 검증.

### Phase 4: Services Reorganization (`services/`)
- Dashboard backend/frontend, ChatA, ChatB를 Green 경로로 복제하고 각각 독립 컨테이너 경계로 유지하면서 Core와 기존 API/schema에 연결한다. 원본 bind mount는 건드리지 않고 서비스별 secret allowlist를 적용한다.
- 보고서 조회·인용 계약과 기존 RAG 기능을 characterization test로 비교.

### Phase 5: Green Stack Build & Isolated Rehearsal
- 기존 Blue Compose를 변경하지 않고 `docker-compose.green.yml`과 PRODUCTION override에 독립 애플리케이션 컨테이너, read-only model mounts, Redis/ChromaDB 의존성, healthcheck를 구성.
- candidate Nginx 설정을 생성·검사하고 내부 route에서 전환·rollback을 모의 검증한다. 이 단계에서는 운영 Nginx를 reload하지 않는다.

### Phase 6: Full Verification & Quality Gates
- Green에서 전체 회귀, 계약, E2E, 복구, 성능, lock contention, PII/secret leakage, Python lint/type-check, frontend `npm ci`/lint/build와 Compose contract를 `quickstart.md`의 정확한 명령으로 실행.
- Performance Baseline Matrix별 P95 결과, 중복 제거율, build context 크기, PII/무환각/citation 결과, 복구 결과를 artifact로 보존.
- 로컬 단일 GTX 1070 결과는 DEMO에만 인정하고, PRODUCTION은 서로 다른 GPU instance의 Gateway endpoint 2개 이상과 Redis primary+replica+Sentinel quorum 또는 동등한 managed HA가 확인된 승인 환경에서만 판정.

### Phase 7: Cutover, 24h Soak & Approved Decommission
- 이 단계는 operator-gated다. 자동 구현은 외부 승인 artifact를 검증할 수 있을 뿐 생성할 수 없다. Green 전체 gate와 외부 cutover 승인을 재확인하고 Blue background writer drain·fresh backup·호환 migration·v1/v2 final delta sync를 완료한 뒤에만 원자적으로 Nginx upstream을 전환하고 post-cutover smoke test를 수행한다.
- 최소 24시간 Blue rollback 경로를 유지하며 오류 임계값과 외부 5xx를 관찰하고 rollback rehearsal을 완료한다.
- 외부 decommission 승인 후에만 Blue를 중지하고 레거시 폴더·설정을 recoverable archive로 이동한다. 운영 volume·snapshot의 영구 삭제는 이 피처 범위에 포함하지 않는다.
