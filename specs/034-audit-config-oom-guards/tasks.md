# Tasks: Audit, Zero-Hardcoding, and Hardware-Tiered Dynamic Context OOM Hardening

**Input**: Design documents from `specs/034-audit-config-oom-guards/`  
**Prerequisites**: [plan.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/plan.md), [spec.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/spec.md), [data-model.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/data-model.md), [research.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/research.md), [contracts/audit_integrity_contract.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/contracts/audit_integrity_contract.md)

---

## Task Execution Format: `- [ ] [TaskID] [P?] [Story?] Description with file path`

---

## Phase 1: Setup & Pre-flight Static Audit Scripts

**Purpose**: 전사 코드베이스에서 레거시 하드코딩 문자열 및 설정 덮어쓰기 패턴을 스캔하는 정적 감사 스크립트 구축

- [ ] T001 전사 소스코드 및 테스트 파일 대상 하드코딩 패턴(`qwen3.5-4b`, 포트, VRAM 상수) 정적 스캔 스크립트 작성 in `model_gateway/scripts/scan_hardcoding.py`
- [ ] T002 [P] `DynamicHardwareProfile` 및 `HardwareTierEnum` Pydantic v2 데이터 모델 정의 in `model_gateway/src/core/gpu_detector.py`
- [ ] T003 [P] `model_gateway/config/server_config.json` 및 `model_context_profiles.json`에 동적 VRAM 사이징 프로파일 스키마 동기화 in `model_gateway/config/server_config.json`

---

## Phase 2: Foundational & TDD Contract Tests

**Purpose**: 동적 컨텍스트 사이징, FlashAttention 조건부 활성화, 하드코딩 부재 검증 단위 테스트 선행 작성 (TDD)

- [ ] T004 [P] VRAM 기반 동적 컨텍스트 윈도우 계산식(`calculate_dynamic_context_window`) 및 티어 분류 단위 테스트 작성 in `model_gateway/tests/test_dynamic_context_sizing.py`
- [ ] T005 [P] GPU Compute Capability에 따른 FlashAttention 생략 및 Q8 KV 옵션 주입 단위 테스트 작성 in `model_gateway/tests/test_hardware_aware_flags.py`
- [ ] T006 [P] 전사 설정 단일 진실 소스(`ConfigManager`) 반환값 일관성 및 Anti-Shadowing 단위 테스트 작성 in `model_gateway/tests/test_config_hierarchy.py`

**Checkpoint**: Foundational TDD 테스트 구축 완료 ➔ 사용자 스토리 구현 착수

---

## Phase 3: User Story 1 (Priority: P1) - VRAM 기반 동적 모델 & 컨텍스트 자동 벤치마킹 서빙 엔진 🎯 MVP

**Goal**: 물리 VRAM 실측값 및 가용 메모리 예산 수식에 따라 최적 모델(2B/4B/9B)과 최대 안전 컨텍스트 윈도우(16K~128K)를 동적으로 산출하여 서빙 바인딩

**Independent Test**: 모의 VRAM 환경(8GB, 11GB, 12GB, 24GB)을 주입하여 `ConfigManager` 및 `gpu_detector.py`가 산출하는 `active_model`과 `current_n_ctx`가 하드웨어 티어 매트릭스와 100% 일치하는지 검증

- [ ] T007 [P] [US1] `gpu_detector.py`에 물리 VRAM 및 CUDA Compute Capability 실측 로직과 `calculate_dynamic_context_window()` 구현 in `model_gateway/src/core/gpu_detector.py`
- [ ] T008 [US1] `ConfigManager`에 동적 VRAM 예산 수식 기반 `get_dynamic_serving_profile()` 메서드 구현 in `model_gateway/src/core/config_manager.py`
- [ ] T009 [US1] `llama_manager.py` 기동 시 동적으로 산출된 $n_{\text{ctx}}$(16K~128K)를 서버 프로세스 인자로 자동 바인딩 in `model_gateway/src/core/llama_manager.py`
- [ ] T010 [US1] `GET /v1/profile` 엔드포인트에 `hardware` 실측 및 `dynamic_n_ctx_max` 필드 연동 in `model_gateway/src/api/routes/inference_api.py`

**Checkpoint**: User Story 1 (MVP) 완결 ➔ 동적 컨텍스트 사이징 엔진 정상 작동

---

## Phase 4: User Story 2 (Priority: P2) - 전사 레거시 하드코딩 전수 점검 및 단일 진실 소스화

**Goal**: `model_gateway`, `bteam/oliview_core`, `ateam/pilos`, 전사 테스트 스위트에 산재한 레거시 하드코딩 문자열을 `ConfigManager`로 완전 일원화

**Independent Test**: 정적 코드 스캔 스크립트(`scan_hardcoding.py`)를 실행하여 하드코딩된 레거시 fallback 문자열이 0건임을 확인

- [ ] T011 [P] [US2] `inference_api.py` 내부의 fallback 모델명(`qwen3.5-4b`)을 `ConfigManager.get_default_model()`로 교체 in `model_gateway/src/api/routes/inference_api.py`
- [ ] T012 [P] [US2] `health_api.py`의 하드코딩된 디바이스명/VRAM을 `get_nvml_vram_info()` 실측값으로 동적 교체 in `model_gateway/src/api/routes/health_api.py`
- [ ] T013 [US2] `ateam/scripts/test_llm_connection.py` 및 `pilos/` 내 모델명 참조를 환경변수 및 동적 탐색으로 교체 in `ateam/scripts/test_llm_connection.py`
- [ ] T014 [US2] `tests/` 디렉토리 내 레거시 계약 테스트 파일들의 정적 모델 어설션을 동적 프로파일 규격으로 동기화 in `tests/test_tiered_routing_contract.py`

**Checkpoint**: User Story 2 완결 ➔ 전사 하드코딩 0건 및 SSOT 규격 확립

---

## Phase 5: User Story 3 (Priority: P3) - 하드웨어 인식 FlashAttention 조건부 활성화 및 Pascal Q8 KV 최적화

**Goal**: GPU Compute Capability를 감지하여 GTX 1070(SM 6.1)에서는 FlashAttention을 생략하고 Q8_0 KV Cache를 적용하며, SM >= 8.0에서는 FlashAttention-3을 자동 활성화

**Independent Test**: GTX 1070 환경에서 기동 로그를 확인하여 FlashAttention 경고 없이 Q8_0 KV Cache가 적용되는지 검증

- [ ] T015 [P] [US3] `process_manager.py`의 `build_server_command`에서 Compute Capability < 8.0 감지 시 `--flash_attn` 생략 및 `--cache-type-k q8_0 --cache-type-v q8_0` 주입 구현 in `model_gateway/src/core/process_manager.py`
- [ ] T016 [US3] Compute Capability >= 8.0 (RTX 3060 이상) 감지 시 `--flash_attn True` 자동 주입 가드 구현 in `model_gateway/src/core/process_manager.py`
- [ ] T017 [US3] GTX 1070 컨테이너에서 llama-server 재기동 시 FlashAttention 경고 0건 및 Q8_0 KV Cache 정상 적용 실측 검증 in `specs/034-audit-config-oom-guards/quickstart.md`

**Checkpoint**: User Story 3 완결 ➔ 하드웨어 인식 FlashAttn/Q8 KV 최적화 완료

---

## Phase 6: User Story 4 (Priority: P4) - 설정 덮어쓰기(Anti-Shadowing) 방어 및 OOM 리소스 누수 격리

**Goal**: 함수 기본 인자(4096)에 의한 덮어쓰기를 차단하고, 좀비 프로세스 VRAM 누수 및 로딩 중 Cascade Kill 방어

**Independent Test**: 다중 동시 추론 및 프로세스 재기동 시 VRAM 누수와 설정 변조가 0건인지 카오스 테스트로 검증

- [ ] T018 [P] [US4] `inference_api.py` 및 `llama_manager.py`에서 요청에 `n_ctx`가 생략된 경우 동적 활성 컨텍스트(16K~32K)를 무변조 주입하도록 가드 강화 in `model_gateway/src/api/routes/inference_api.py`
- [ ] T019 [US4] `llama_manager.py`의 `LOADING` 상태 가드를 강화하여 중복 요청 시 기존 프로세스 종료 없이 `_wait_for_ready` 대기하도록 방어 in `model_gateway/src/core/llama_manager.py`
- [ ] T020 [US4] 서브프로세스 종료 시 소켓 바인딩 해제 확인 및 미종료 프로세스 `SIGKILL` 강제 회수 로직 구현 in `model_gateway/src/core/process_manager.py`

**Checkpoint**: User Story 4 완결 ➔ Anti-Shadowing 및 OOM 리소스 누수 원천 격리

---

## Phase 7: Polish & 전사 5대 종합 회귀 테스트 및 라이브 검증

**Purpose**: 전사 통합 회귀 검증 및 문서 동기화 완결

- [ ] T021 [P] Model Gateway 신규 단위/계약 테스트 전체 실행 및 100% 통과 확인 in `model_gateway/tests/`
- [ ] T022 전사 5대 종합 회귀 테스트 스위트([run_all_regression_tests.py](file:///c:/AISERVICE/bteam/tests/run_all_regression_tests.py)) 실행 및 100% 통과 확인 in `bteam/tests/run_all_regression_tests.py`
- [ ] T023 [quickstart.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/quickstart.md)에 실시간 실행 로그 및 실측 지표 기록 완료 in `specs/034-audit-config-oom-guards/quickstart.md`

---

## Dependencies & User Story Completion Order

```mermaid
flowchart TD
    Setup[Phase 1: Setup & Static Audit Script] --> Foundational[Phase 2: Foundational & TDD Tests]
    Foundational --> US1[Phase 3: US1 - VRAM 기반 동적 컨텍스트 사이징 (MVP)]
    US1 --> US2[Phase 4: US2 - 전사 레거시 하드코딩 제거]
    US2 --> US3[Phase 5: US3 - 하드웨어 인식 FlashAttn & Q8 KV]
    US3 --> US4[Phase 6: US4 - Anti-Shadowing & OOM 방어]
    US4 --> Polish[Phase 7: 전사 5대 회귀 테스트 & 검증 완결]
```
