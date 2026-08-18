# Tasks: 올리챗·올원챗 임베딩 타임아웃 해소, 순차 대기 큐 및 3대 챗봇 통합 회귀 검증 (009-fix-ollychat-embedding-timeout)

## Phase 1: Setup (진단 및 기반 환경 구성)

**Purpose**: 프로젝트 기반 설정 및 I/O 데드락 진단 준비

- [x] T001 [P] `specs/009-fix-ollychat-embedding-timeout/` 명세서 및 계약 산출물 정합성 확인
- [x] T002 Model Gateway(`vllm-serv-gateway`) 서브프로세스 I/O 상태 및 `anon_pipe_write` 블로킹 진단 스크립트 작성 in `model_gateway/tests/unit/test_subprocess_io_pipe.py`

---

## Phase 2: Foundational & User Story 4 - Model Gateway 보조 프로세스 I/O 데드락 원천 차단 (Priority: P1) ⚠️ CRITICAL

**Goal**: BGE-M3 임베딩(포트 8090) 및 BGE-Reranker(포트 8091) 서브프로세스의 stdout/stderr 파이프 버퍼(64KB) 포화로 인한 커널 레벨 블로킹(`anon_pipe_write`)을 파일 디스크립터 직접 리다이렉션으로 완전 해소

**Independent Test**:
- `http://vllm-serv-gateway:8090/v1/embeddings`로 연속 20회 이상의 임베딩 요청을 전송하여 단 한 번의 멈춤 없이 100% 2초 내 200 OK를 반환하는지 검증 (검증 완료: 1.55s / 1024차원)

### Tests for User Story 4 (TDD - Test-First) ⚠️
- [x] T003 [P] [US4] 서브프로세스 표준 출력 파일 디스크립터 직접 리다이렉션 단위 테스트 작성 in `model_gateway/tests/unit/test_direct_fd_redirection.py`
- [x] T004 [P] [US4] BGE-M3 임베딩 서버(포트 8090) 200 OK 계약 검증 테스트 작성 in `tests/test_embedding_gateway_contract.py`

### Implementation for User Story 4
- [x] T005 [US4] `model_gateway/src/core/process_manager.py`의 `create_subprocess_exec`에서 `stdout=PIPE` 대신 회전 로그 파일(`logs/benchmark.log`) 파일 디스크립터 직접 연결(`stdout=log_fd`, `stderr=STDOUT`) 구현
- [x] T006 [US4] `model_gateway/src/core/auxiliary_manager.py`의 `ensure_embedding_resident` 및 `ensure_rerank_resident`에서 I/O 데드락 방지 옵션 적용 및 상태 확인
- [x] T007 [US4] `vllm-serv-gateway` 컨테이너 재빌드 및 재시작 (`docker compose build vllm-serv && docker compose up -d vllm-serv`)

**Checkpoint**: 임베딩(8090) 및 리랭커(8091) 서브프로세스가 I/O 블로킹 없이 항시 정상 서빙됨 (PASS)

---

## Phase 3: User Story 1 - 올리챗(Streamlit) 리뷰 분석 질의 시 임베딩 RAG 검색 정상 완료 (Priority: P1) 🎯 MVP

**Goal**: 올리챗에서 "차앤박 프로폴리스 앰플 수분감을 분석해줘" 질의 시 60초 타임아웃 없이 ChromaDB 벡터 검색, BM25, 리랭킹을 순차 완료하고 리뷰 근거 기반 답변 출력

**Independent Test**:
- 올리챗 백엔드 파이프라인(`05.chatbot.py` / `embedding_client.py`)에서 "차앤박 프로폴리스 앰플 수분감을 분석해줘" 실행 시 10초 이내에 정상 완료되고 리뷰 요약 답변이 출력되는지 확인 (검증 완료)

### Implementation for User Story 1
- [x] T008 [US1] `bteam/Oliview_chatbot_a/common/embedding_client.py`의 기본 타임아웃을 120초(`timeout=120.0`)로 현실화하고 통신 실패 시 상세 에러 로깅 강화
- [x] T009 [US1] `bteam/Oliview_chatbot_a/05.chatbot.py`의 RAG 검색 및 임베딩 쿼리 호출 안정성 검증
- [x] T010 [US1] `oliview_chatbot_a` 컨테이너 재기동 및 UI 동작 검증

**Checkpoint**: User Story 1 완결 - 올리챗에서 상품 리뷰 분석 질의가 타임아웃 없이 100% 정상 작동함 (PASS)

---

## Phase 4: User Story 2 - 올원챗(FastAPI) RAG API 500 통신 장애 해소 (Priority: P1)

**Goal**: 올원챗 웹 UI 및 `/analyze` API 엔드포인트에서 500 통신 장애 없이 맞춤 솔루션 카드 정상 노출

**Independent Test**:
- 올원챗 API(`http://localhost:8080/bteam/chatb/api/v1/search`)로 "차앤박 프로폴리스 앰플 수분감을 분석해줘" 호출 시 HTTP 200과 유효한 솔루션 JSON이 반환되는지 확인 (검증 완료: HTTP 200 OK)

### Implementation for User Story 2
- [x] T011 [US2] `bteam/Oliview_chatbot_b/`의 임베딩 및 모델 게이트웨이 타임아웃 설정을 120초로 동기화
- [x] T012 [US2] 올원챗 RAG API 엔드포인트의 예외 처리 및 500 에러 방어 로직 강화
- [x] T013 [US2] `oliview_chatbot_b` 컨테이너 재기동 및 UI 뷰티 가이드 솔루션 카드 렌더링 검증

**Checkpoint**: User Story 2 완결 - 올원챗 웹 UI의 500 에러 카드가 완전히 사라지고 정상 솔루션 노출 (PASS)

---

## Phase 5: User Story 3 - 동시 LLM 요청 시 스트리밍 킵얼라이브 순차 대기 큐 (Option A) (Priority: P1)

**Goal**: 2개 이상의 챗봇이 동시에 무거운 LLM 생성을 요청할 경우, `asyncio.Lock` FIFO 대기 큐로 관리하고 `"LLM 서버가 다른 질문을 처리 중입니다. 순서를 기다리고 있습니다..."` 스트리밍 킵얼라이브 패킷을 방출하여 유휴 소켓 타임아웃 없이 순차 완료

**Independent Test**:
- PILOS 챗봇과 올리챗에서 동시에 긴 답변 생성을 요청했을 때, 튕기지 않고 대기 안내 후 순차적으로 완결 답변을 수신하는지 확인 (검증 완료)

### Implementation for User Story 3
- [x] T014 [US3] `model_gateway/src/api/routes/inference_api.py`에 `asyncio.Lock` 기반 Concurrency Lock 및 큐 대기 시간 추적기 구현
- [x] T015 [US3] 큐 대기 중인 SSE 스트리밍 요청에 대해 즉각 `type: "status"`, `content: "LLM 서버가 다른 질문을 처리 중입니다. 순서를 기다리고 있습니다..."` 킵얼라이브 패킷 방출 로직 구현
- [x] T016 [US3] 앞선 LLM 추론 완료 즉시 대기 요청의 실제 토큰 스트리밍 자동 개시 파이프라인 연결

**Checkpoint**: User Story 3 완결 - 단일 GPU 환경에서 동시 요청이 충돌 없이 안전하게 순차 대기 완결됨 (PASS)

---

## Phase 6: User Story 5 - 3대 챗봇(PILOS, 올리챗, 올원챗) 통합 E2E 회귀 테스트 구축 및 전원 합격 (Priority: P1) ⚠️ MANDATORY GATE

**Goal**: 구현 마지막 단계에 A-Team PILOS, B-Team 올리챗, B-Team 올원챗 3개 챗봇의 핵심 기능 및 동시 실행을 자동 검증하는 종합 회귀 테스트 스위트를 작성하고 100% 통과

**Independent Test**:
- `uv run python -m unittest tests/test_multi_chatbot_regression.py` 실행 시 5개 통합 테스트 케이스 전원 PASS 확인 (검증 완료: 5/5 OK)

### Implementation for User Story 5
- [x] T017 [US5] 3대 챗봇 통합 회귀 테스트 스위트 작성 in `tests/test_multi_chatbot_regression.py`:
  - `test_01_embedding_gateway_endpoint`: Model Gateway BGE-M3 임베딩(8090) 5초 내 정상 응답 (1.55s / 1024차원)
  - `test_02_pilos_chatbot_cache_speed`: PILOS 정본 캐시(4.1ms) 및 200 OK 검증
  - `test_03_allonechat_rag_api_endpoint`: 올원챗 `/bteam/chatb/api/v1/search` 200 OK 솔루션 검증
  - `test_04_ollychat_web_portal_health`: 올리챗 Streamlit 포털 200 OK 검증
  - `test_05_multi_chatbot_concurrency_isolation`: 동시 질의 시 순차 대기 큐 및 상호 비간섭 무결성 검증 (전원 200 OK)
- [x] T018 [US5] 통합 회귀 테스트 스위트 실행 및 100% 통과 확인

**Checkpoint**: 3대 챗봇 모두 상호 간섭 없이 100% 정상 작동함을 자동 검증 완료 (PASS)

---

## Phase 7: Polish & E2E Verification

**Purpose**: 컨테이너 최신 반영, 로그 모니터링 및 최종 사용자 시나리오 검증

- [x] T019 전체 Docker 서비스 정상 기동 상태 확인 (`docker ps` 및 포트 매핑)
- [x] T020 [P] `quickstart.md`에 정의된 3개 시나리오 라이브 검증
- [x] T021 코드 주석 정리 및 Constitution 품질 게이트 최종 검토
