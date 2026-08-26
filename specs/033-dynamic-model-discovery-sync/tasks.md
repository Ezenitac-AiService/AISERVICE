# Tasks: Dynamic Model Discovery & Hardware-Aware Synchronization

**Input**: Design documents from `specs/033-dynamic-model-discovery-sync/`  
**Prerequisites**: [plan.md](file:///c:/AISERVICE/specs/033-dynamic-model-discovery-sync/plan.md), [spec.md](file:///c:/AISERVICE/specs/033-dynamic-model-discovery-sync/spec.md), [data-model.md](file:///c:/AISERVICE/specs/033-dynamic-model-discovery-sync/data-model.md), [research.md](file:///c:/AISERVICE/specs/033-dynamic-model-discovery-sync/research.md), [contracts/model_discovery_contract.md](file:///c:/AISERVICE/specs/033-dynamic-model-discovery-sync/contracts/model_discovery_contract.md)

---

## Task Execution Format: `- [x] [TaskID] [P?] [Story?] Description with file path`

---

## Phase 1: Setup & Environment Configuration Synchronization

**Purpose**: 전사 환경 설정 파일(`.env`, `docker-compose.yml`, `config.json`)을 `qwen3.5-2b (16K ctx)` 표준 규격으로 일원화

- [x] T001 루트 `.env` 파일에 `SYNTHESIS_LLM_MODEL=qwen3.5-2b` 및 `FAST_LLM_MODEL=qwen3.5-2b` 일원화 설정 적용 in `.env`
- [x] T002 `docker-compose.yml`의 `vllm-serv`, `oliview_chatbot_a`, `oliview_chatbot_b` 환경변수 기본값을 `qwen3.5-2b`로 동기화 in `docker-compose.yml`
- [x] T003 [P] `model_gateway/config/server_config.json` 및 `model_gateway/config/model_config.json`에 `default_model: qwen3.5-2b`, `current_n_ctx: 16384` 설정 확인 및 동기화 in `model_gateway/config/server_config.json`

---

## Phase 2: Foundational & TDD Contract Tests

**Purpose**: 모델 탐색 엔드포인트 및 클라이언트 캐싱 인터페이스에 대한 테스트 선행 구축 (TDD 원칙 준수)

- [x] T004 [P] 게이트웨이 `GET /v1/models` 및 `GET /v1/profile` 엔드포인트 계약 검증 단위 테스트 작성 in `model_gateway/tests/test_model_discovery_contract.py`
- [x] T005 [P] 클라이언트 `discover_active_model()` 60초 TTL 캐싱 및 안전 폴백 단위 테스트 작성 in `bteam/tests/test_dynamic_discovery_client.py`
- [x] T006 [P] 비상주 `qwen3.5-4b` 요청 시 상주 `qwen3.5-2b (16K)` 투명 매핑 단위 테스트 검증 in `model_gateway/tests/test_single_model_mode.py`

**Checkpoint**: Foundational TDD 테스트 작성 완료 ➔ 사용자 스토리 구현 시작

---

## Phase 3: User Story 1 (Priority: P1) - 클라이언트 동적 모델 탐색 & 60초 TTL 캐싱 🎯 MVP

**Goal**: 챗봇 클라이언트 라이브러리가 게이트웨이의 활성 모델을 동적으로 탐색하고 60초 TTL로 캐싱하여 RAG 답변 합성에 자동 바인딩

**Independent Test**: 클라이언트 환경변수를 지정하지 않거나 임의의 값을 주더라도 `discover_active_model()`을 통해 게이트웨이 활성 모델(`qwen3.5-2b`)을 획득하고 0ms 오버헤드로 RAG 스트리밍을 완결하는지 검증

- [x] T007 [P] [US1] `ModelDiscoveryCache` 엔티티 및 동적 탐색 설정 필드를 `CoreSettings`에 추가 in `bteam/oliview_core/config.py`
- [x] T008 [US1] `AiGatewayClient.discover_active_model(force_refresh=False)` 동적 탐색 및 인메모리 60초 TTL 캐싱 메서드 구현 in `bteam/oliview_core/client.py`
- [x] T009 [US1] RAG 답변 합성 노드([synthesis_node.py](file:///c:/AISERVICE/bteam/oliview_core/nodes/synthesis_node.py))에 동적 모델 바인딩을 적용하고 챗봇 A/B에 동기화 in `bteam/oliview_core/nodes/synthesis_node.py`
- [x] T010 [US1] 챗봇 B 컨테이너에서 `discover_active_model()` 실행 및 캐시 갱신 독립 테스트 수행 in `specs/033-dynamic-model-discovery-sync/quickstart.md`

**Checkpoint**: User Story 1 (MVP) 완결 ➔ 클라이언트 동적 탐색 및 0ms 캐싱 정상 작동

---

## Phase 4: User Story 2 (Priority: P2) - 게이트웨이 하드웨어 프로파일 & 메타데이터 노출

**Goal**: 모델 게이트웨이가 현재 GPU VRAM 현황, 16K 컨텍스트 윈도우, 상주 활성 모델 메타데이터를 공식 API로 제공

**Independent Test**: `GET /v1/profile` 및 `GET /v1/models` 호출 시 `is_active: true`, `current_n_ctx: 16384`, `vram_total_mb`가 정확히 반환되는지 검증

- [x] T011 [P] [US2] `GET /v1/profile` 엔드포인트를 구현하여 GPU VRAM 및 상주 모델 상태 노출 in `model_gateway/src/api/routes/inference_api.py`
- [x] T012 [US2] `GET /v1/models` 응답에 `is_active`, `is_resident`, `current_n_ctx` 메타데이터 필드 보강 in `model_gateway/src/api/routes/inference_api.py`
- [x] T013 [US2] 게이트웨이 컨테이너에서 `GET /v1/models` 및 `GET /v1/profile` curl/python 독립 검증 수행 in `specs/033-dynamic-model-discovery-sync/quickstart.md`

**Checkpoint**: User Story 2 완결 ➔ 게이트웨이 프로파일 API 공식 제공

---

## Phase 5: User Story 3 (Priority: P3) - 레거시/비상주 모델 요청 투명 재매핑 & 로딩 보호

**Goal**: 클라이언트나 외부 스크립트가 `qwen3.5-4b`를 명시하여 요청하더라도 게이트웨이가 프로세스 킬 없이 상주 `qwen3.5-2b (16K)`로 즉시 투명 라우팅

**Independent Test**: `model: "qwen3.5-4b"` 페이로드로 `POST /v1/chat/completions` 호출 시 500 에러나 프로세스 재시작 없이 200 OK와 스트리밍 응답이 반환되는지 검증

- [x] T014 [P] [US3] `reverse_proxy`의 `SINGLE_MODEL_MODE=true` 가드에서 비상주 모델 요청 본문을 상주 모델(`qwen3.5-2b`)로 투명 치환하고 `x-model-served` 응답 헤더 추가 in `model_gateway/src/api/routes/inference_api.py`
- [x] T015 [US3] `llama_manager.py`의 `LOADING` 상태 보호 가드를 통해 프로세스 로딩 도중 요청 유입 시 기존 프로세스 종료 없이 대기(`_wait_for_ready`)하도록 방어 in `model_gateway/src/core/llama_manager.py`
- [x] T016 [US3] 챗봇 B에서 `model: "qwen3.5-4b"` 페이로드 호출 및 200 OK 무중단 스트리밍 독립 검증 수행 in `specs/033-dynamic-model-discovery-sync/quickstart.md`

**Checkpoint**: User Story 3 완결 ➔ 4B 레거시 요청 100% 무중단 투명 매핑 달성

---

## Phase 6: User Story 4 (Priority: P4) - 16K 대용량 컨텍스트 상주 보장 & 초장문 스케일다운 가드

**Goal**: 2B 모델이 4B 업무를 완전 수용하도록 16K 대용량 컨텍스트를 상주 보장하고, 32K~64K 초장문 작업 시 경량 모델로 동적 스케일다운 지원

**Independent Test**: 16K 대용량 컨텍스트 상태에서 실시간 LLM 토큰 생성 속도가 20+ tok/s로 안정 출력되는지 검증

- [x] T017 [P] [US4] `llama_manager.py` 및 `process_manager.py`에서 기본 컨텍스트 윈도우 크기를 `16384`로 엄격 고정 및 임의 축소 금지 in `model_gateway/src/core/llama_manager.py`
- [x] T018 [US4] 초장문 컨텍스트($n_{\text{ctx}} > 16384$) 요청 유입 시 VRAM OOM 방지를 위한 경량 모델 스케일다운 가드 구조 보강 in `model_gateway/src/core/llama_manager.py`
- [x] T019 [US4] 16K 컨텍스트 환경에서 실시간 토큰 스트리밍 속도(20+ tok/s) 및 VRAM 안정성 독립 검증 수행 in `specs/033-dynamic-model-discovery-sync/quickstart.md`

**Checkpoint**: User Story 4 완결 ➔ 16K 대용량 컨텍스트 및 초장문 확장성 확보

---

## Phase 7: Polish & 전사 5대 종합 회귀 테스트 검증

**Purpose**: 변경 사항에 대한 통합 회귀 검증 및 문서 동기화 완결

- [x] T020 [P] Model Gateway 전체 단위/통합 테스트 스위트 실행 및 100% 통과 확인 in `model_gateway/tests/`
- [x] T021 5대 종합 회귀 테스트 스위트([run_all_regression_tests.py](file:///c:/AISERVICE/bteam/tests/run_all_regression_tests.py)) 실행 및 100% 통과 확인 in `bteam/tests/run_all_regression_tests.py`
- [x] T022 [quickstart.md](file:///c:/AISERVICE/specs/033-dynamic-model-discovery-sync/quickstart.md)에 실시간 실행 로그 및 실측 지표 기록 완료 in `specs/033-dynamic-model-discovery-sync/quickstart.md`

---

## Dependencies & User Story Completion Order

```mermaid
flowchart TD
    Setup[Phase 1: Setup & Env Sync] --> Foundational[Phase 2: Foundational & TDD Tests]
    Foundational --> US1[Phase 3: US1 - 클라이언트 동적 탐색 & 60s TTL 캐싱 (MVP)]
    US1 --> US2[Phase 4: US2 - 게이트웨이 하드웨어 프로파일 노출]
    US2 --> US3[Phase 5: US3 - 레거시 모델 투명 매핑 & 로딩 가드]
    US3 --> US4[Phase 6: US4 - 16K 컨텍스트 상주 & 초장문 가드]
    US4 --> Polish[Phase 7: 전사 5대 회귀 테스트 & 검증 완결]
```
