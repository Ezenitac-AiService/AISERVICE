# Tasks: A-Team Pilos 댓글 크롤러 로직 전면 재점검 및 18~19일 결손 정합성 복원

**Feature**: `023-pilos-crawler-collection-audit`
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 테스트 환경 및 크롤러 결손 분석 공통 하네스 구성

- [x] T001 [P] Review interface contracts in `specs/023-pilos-crawler-collection-audit/contracts/crawler_contracts.md`
- [x] T002 [P] Verify MySQL connection and check current `preprocessed_comment` 18~19th date distribution baseline

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 비식별화 fallback 및 크롤러 파싱 예외 처리 기반 구축

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 Implement `anonymize_user_profile_id()` and `anonymize_nickname()` default fallbacks (`ANONYMOUS_USER`, `익명`) in `ateam/pilos-sentiment-index/pilos/collection/data_masking.py`
- [x] T004 [P] Update `BASE_TIME` constant to 0.5s with random jitter in `ateam/pilos-sentiment-index/pilos/collection/constants.py`
- [x] T005 [P] Create initial unit test suite in `ateam/pilos-sentiment-index/tests/collection/test_crawler_audit.py`

**Checkpoint**: Foundation ready - de-identification fallbacks and test harness operational

---

## Phase 3: User Story 1 - 증분 및 백필 크롤링 필터링 결손 제거 및 수집량 정상화 (Priority: P1) 🎯 MVP

**Goal**: `_select_page()`에서 비필수 작성자 필드 누락으로 인한 댓글 버림 결함을 수정하고 대댓글/답글을 포함한 모든 유효 댓글을 100% 수집

**Independent Test**: 비정형 메타데이터(프로필 ID 결측, 닉네임 결측) 및 대댓글이 포함된 모의 API 응답을 파싱하여 드롭률 0.0% 검증

### Tests for User Story 1

- [x] T006 [P] [US1] Unit test for missing `authorUserProfileId`/`nickname` fallback parsing in `ateam/pilos-sentiment-index/tests/collection/test_crawler_audit.py`
- [x] T007 [P] [US1] Unit test for nested sub-comments (대댓글) flattening in `ateam/pilos-sentiment-index/tests/collection/test_crawler_audit.py`

### Implementation for User Story 1

- [x] T008 [US1] Refactor `_select_page()` in `ateam/pilos-sentiment-index/pilos/collection/comment_crawler.py` to ensure `last_cursor` always advances and records are preserved with default fallback
- [x] T009 [US1] Implement sub-comments/replies extraction and flattening in `_select_page()` in `ateam/pilos-sentiment-index/pilos/collection/comment_crawler.py`
- [x] T010 [US1] Update `DatePartitionedAppender` in `ateam/pilos-sentiment-index/pilos/storage/comment_store.py` to seamlessly route flattened sub-comments by `createdAt`

**Checkpoint**: User Story 1 (MVP) complete - crawler captures 100% of comments without dropping records

---

## Phase 4: User Story 2 - 18일~19일 결손 데이터 소급 재수집 및 파이프라인 정합성 복원 (Priority: P2)

**Goal**: 10개 전 종목을 대상으로 2026-08-18 00:00(KST)까지 일괄 소급 백필을 수행하고 7단계 서비스 파이프라인을 엔드투엔드로 연속 실행하여 감성지표 및 LLM 보고서 완전 복원

**Independent Test**: 백필 CLI 실행 후 `preprocessed_comment` 적재 건수 증가 및 18~19일 일별 감성 보고서 생성 확인

### Tests for User Story 2

- [x] T011 [P] [US2] Integration test for multi-stock batch backfill execution in `ateam/pilos-sentiment-index/tests/collection/test_crawler_audit.py`

### Implementation for User Story 2

- [x] T012 [US2] Enhance `pilos/jobs/backfill_comments.py` CLI to support `--target all` (10 stocks batch) and robust stop condition
- [x] T013 [US2] Update `pilos/jobs/run_service_pipeline.py` to support post-backfill end-to-end cascade trigger (preprocessing -> tokenization -> daily docs -> supply/demand -> Ridge -> LLM reports)
- [x] T014 [US2] Execute live catch-up backfill for 10 stocks in `pilos_worker` container (`--until-date 2026-08-18 --target all`)
- [x] T015 [US2] Execute end-to-end service pipeline cascade in `pilos_worker` container

**Checkpoint**: User Stories 1 AND 2 complete - 18~19th data fully restored across all 10 stocks

---

## Phase 5: User Story 3 - 크롤러 안정성 강화 및 관측 지표 로깅 (Priority: P3)

**Goal**: 크롤링 실행 시 일별 수집량, API 호출 페이지 수, 종목별 최근 수집 ID(`recent_comment_id`)를 구조화 로깅하여 관측성 확보

**Independent Test**: 실행 로그에 각 종목별 수집 통계 및 매니페스트 갱신 정보가 누락 없이 기록되는지 검증

### Tests for User Story 3

- [x] T016 [P] [US3] Unit test for crawler metrics logging and manifest synchronization in `ateam/pilos-sentiment-index/tests/collection/test_crawler_audit.py`

### Implementation for User Story 3

- [x] T017 [US3] Add structured metric summary logging in `pilos/collection/comment_crawler.py`
- [x] T018 [US3] Ensure `worker_daemon.py` periodically logs healthy collection summaries without errors

**Checkpoint**: All user stories functional with high observability

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 도커 컨테이너 동기화, DB 데이터 검증 쿼리 수행 및 최종 통합 보고서 작성

- [x] T019 [P] Rebuild and restart `pilos-web` and `pilos-worker` Docker containers
- [x] T020 Run DB verification query on `pilos_db` to assert 18~19th comment counts match expectations
- [x] T021 Run quickstart validation scenarios per `specs/023-pilos-crawler-collection-audit/quickstart.md`
- [x] T022 Document walkthrough and create final verification report

---

## Dependencies & Execution Order

- **Phase 1 (Setup)** -> **Phase 2 (Foundational)** -> **Phase 3 (User Story 1 - MVP)** -> **Phase 4 (User Story 2)** -> **Phase 5 (User Story 3)** -> **Phase 6 (Polish)**
