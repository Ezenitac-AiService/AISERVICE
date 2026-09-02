# Tasks: Oliview B-Team RAG 파이프라인 DB/리랭커 복구 및 64K q8_0 KV 양자화 OOM 방지 (Feature 045)

**Feature Branch**: `045-fix-bteam-rag-zero-search`
**Specification**: [spec.md](./spec.md)
**Implementation Plan**: [plan.md](./plan.md)

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 프로젝트 환경 및 진단 기반 검증

- [X] T001 64K q8_0 KV 캐시 및 B-Team DB 스키마 복구 대상 파일 상태 확인

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 모델 게이트웨이 64K 양자화 및 자가치유 루틴 기반 마련 (모든 사용자 스토리 선행)

- [X] T002 [P] `model_gateway/src/core/process_manager.py`의 `build_server_command`에 `n_ctx >= 32768` 모델 대상 `--type_k q8_0 --type_v q8_0` 인자 주입 구현 (FR-003)
- [X] T003 [P] `model_gateway/src/core/auxiliary_manager.py`의 `check_and_recover_crashes`에 UNLOADED/ERROR 상태 자동 스폰 복구 루틴 구현 (FR-004)

**Checkpoint**: 게이트웨이 OOM 방지 및 자가치유 인프라 준비 완료

---

## Phase 3: User Story 1 - 올리뷰 챗봇 A & B DB 메타데이터 및 0건 부재 고지 복구 (Priority: P1) 🎯 MVP

**Goal**: SQL 스키마 불일치 에러(`Unknown column 'p.brand'`)를 해결하여 챗봇 A와 B에서 0건 부재 고지 없이 실제 리뷰 기반 분석 답변 생성

**Independent Test**: `fetch_review_metadata` 실행 시 `Metadata count > 0` 정상 반환 및 챗봇 A/B 질의 시 0건 부재 고지 0건 확인

- [X] T004 [P] [US1] `bteam/oliview_core/db.py`의 `fetch_review_metadata`를 `vw_chroma_review_sentences` 조인 쿼리로 전면 교체 (FR-001)
- [X] T005 [P] [US1] `bteam/Oliview_chatbot_a/oliview_core/db.py`에 수정된 DB 메타데이터 로직 동기화 (FR-005)
- [X] T006 [P] [US1] `bteam/Oliview_chatbot_b/oliview_core/db.py`에 수정된 DB 메타데이터 로직 동기화 (FR-005)
- [X] T007 [US1] 챗봇 A ("브링그린 클렌징 제품 모공 세정 효과 알려줘") RAG 검색 및 메타데이터 E2E 검증 (SC-001, SC-002)
- [X] T008 [US1] 챗봇 B ("여름철 기름기 잡고 모공 커버 잘되는 매트한 파운데이션 추천해줘") RAG 검색 및 메타데이터 E2E 검증 (SC-001, SC-002)

**Checkpoint**: 챗봇 A & B의 0건 부재 고지 해소 및 실질 RAG 응답 정상화 (MVP 달성)

---

## Phase 4: User Story 2 - 64K 풀 컨텍스트 유지 및 q8_0 KV 양자화 OOM 방지 (Priority: P2)

**Goal**: 64K 풀 컨텍스트 서빙 상태에서 3종 모델 상시 상주 및 Linux Kernel OOM Killer(Exit 137) 원천 차단

**Independent Test**: 모델 게이트웨이 8089 프로세스에 `--type_k q8_0 --type_v q8_0` 플래그 적용 확인 및 연속 추론 시 OOM Crash 0건 확인

- [X] T009 [US2] 모델 게이트웨이 컨테이너 재기동 후 `qwen3.5-2b`의 `--type_k q8_0 --type_v q8_0` 플래그 및 VRAM/RAM 점유량 실측 (SC-003)
- [X] T010 [US2] 64K 컨텍스트 연속 추론 부하 시 Linux Kernel OOM Killer(Exit 137) 부재 및 프로세스 생존 검증 (SC-003)

**Checkpoint**: 64K 컨텍스트 안정 서빙 및 OOM-Kill 완전 방지

---

## Phase 5: User Story 3 - GPU 리랭커 안전 Fallback 방어 및 포트 8091 상주 (Priority: P3)

**Goal**: 리랭커 미응답/타임아웃 시 `NoneType` 크래시 방지 및 1차 유사도 순위 무중단 안전 폴백

**Independent Test**: 리랭커 엔드포인트 미응답 모의 시에도 `BGEReranker.rerank()`가 `TypeError` 없이 1차 검색 순위로 완주 확인

- [X] T011 [P] [US3] `bteam/oliview_core/rerank.py`의 `BGEReranker.rerank()`에 `scores is None` 안전 Fallback 방어 코드 구현 (FR-002)
- [X] T012 [P] [US3] `bteam/Oliview_chatbot_a/oliview_core/rerank.py`에 리랭커 안전 Fallback 코드 동기화 (FR-005)
- [X] T013 [P] [US3] `bteam/Oliview_chatbot_b/oliview_core/rerank.py`에 리랭커 안전 Fallback 코드 동기화 (FR-005)
- [X] T014 [US3] 게이트웨이 포트 8091(`bge-reranker-v2-m3`) 상시 가용성 및 리랭킹 점수 E2E 검증 (SC-004, SC-005)

**Checkpoint**: 리랭커 인프라 상시 가용 및 결함 내성(Fault Tolerance) 완성

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 회귀 방지 테스트 및 최종 실측 검증

- [X] T015 [P] 회귀 방지 단위/통합 테스트 작성 (`model_gateway/tests/test_bteam_rag_recovery.py`, `bteam/Oliview_chatbot_a/tests/test_bteam_rag_recovery.py`)
- [X] T016 챗봇 A & 챗봇 B 웹 UI 및 API 전체 RAG 답변 생성 실측 전수 검증 (`quickstart.md`)
- [X] T017 walkthrough.md 작성 및 최종 보고
