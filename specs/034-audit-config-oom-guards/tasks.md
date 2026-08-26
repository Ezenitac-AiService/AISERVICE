# Tasks: Audit, Zero-Hardcoding, and 6-Tier CPU-GPU Paired Architecture OOM Hardening

**Input**: Design documents from `specs/034-audit-config-oom-guards/`  
**Prerequisites**: [plan.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/plan.md), [spec.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/spec.md), [data-model.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/data-model.md), [research.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/research.md), [contracts/audit_integrity_contract.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/contracts/audit_integrity_contract.md)

---

## Task Execution Format: `- [ ] [TaskID] [P?] [Story?] Description with file path`

---

## Phase 1: Setup & 6-Tier CPU-GPU Architecture Specs Setup

**Purpose**: 6대 타겟 CPU-GPU 플랫폼(Tier 1 i7 930+GTX 1070부터 Tier 6 최신 Intel+RTX 5000) 불변 스펙 룩업 테이블 및 정적 감사 스크립트 구축

- [ ] T001 전사 소스코드 및 테스트 파일 대상 하드코딩 패턴(`qwen3.5-4b`, 포트, VRAM 상수) 정적 스캔 스크립트 작성 in `model_gateway/scripts/scan_hardcoding.py`
- [ ] T002 [P] 6대 CPU-GPU 하드웨어 페어링 불변 스펙 룩업 테이블 및 Pydantic v2 데이터 모델 정의 in `model_gateway/src/core/gpu_detector.py`
- [ ] T003 [P] `model_gateway/config/server_config.json` 및 `model_context_profiles.json`에 동적 VRAM 사이징 프로파일 스키마 동기화 in `model_gateway/config/server_config.json`

---

## Phase 2: Foundational & TDD Contract Tests

**Purpose**: 6대 CPU-GPU 아키텍처 자동 감지, i7 930 `-ngl 999` 강제, FlashAttn/Q8/FP8 플래그 주입 TDD 단위 테스트 선행 작성

- [ ] T004 [P] 6대 CPU-GPU 조합 모의 주입 시 아키텍처 매칭 및 VRAM 사이징 단위 테스트 작성 in `model_gateway/tests/test_gpu_architecture_specs.py`
- [ ] T005 [P] i7 930(AVX 없음) 감지 시 `-ngl 999` 강제 및 FlashAttention 생략/활성화 단위 테스트 작성 in `model_gateway/tests/test_hardware_aware_flags.py`
- [ ] T006 [P] 전사 설정 단일 진실 소스(`ConfigManager`) 반환값 일관성 및 Anti-Shadowing 단위 테스트 작성 in `model_gateway/tests/test_config_hierarchy.py`

**Checkpoint**: Foundational TDD 테스트 구축 완료 ➔ 사용자 스토리 구현 착수

---

## Phase 3: User Story 1 (Priority: P1) - 6대 CPU-GPU 페어링 자율 하드웨어 감지 & 최적 서빙 엔진 🎯 MVP

**Goal**: CPU 명령어 세트(AVX 유무)와 GPU Compute Capability 및 물리 VRAM을 실측하여 6대 세대별 불변 체크리스트에 따라 플래그, 모델, 컨텍스트 크기를 100% 자동 구성

**Independent Test**: 모의 하드웨어 스펙(i7 930+GTX 1070, i7+GTX 1080Ti, i7+RTX 3060, Ultra+RTX 5080)을 주입하여 `detect_hardware_capabilities()`가 반환하는 플래그와 모델이 6대 매트릭스와 정확히 일치하는지 검증

- [ ] T007 [P] [US1] `gpu_detector.py`에 CPU AVX 실측 및 GPU Compute Capability/VRAM 실측 기반 `detect_hardware_capabilities()` 룩업 매칭 로직 구현 in `model_gateway/src/core/gpu_detector.py`
- [ ] T008 [US1] `ConfigManager`에 VRAM 예산 수식 기반 `calculate_dynamic_context_window()` 및 동적 프로파일링 메서드 구현 in `model_gateway/src/core/config_manager.py`
- [ ] T009 [US1] `process_manager.py`의 `build_server_command`에서 세대별 최적 플래그(i7 930 `-ngl 999`, SM 6.1 Q8 KV, SM 8.6+ FlashAttn, SM 12.0 FP4/FP8) 자동 주입 구현 in `model_gateway/src/core/process_manager.py`
- [ ] T010 [US1] `GET /v1/profile` 엔드포인트에 `gpu_features`, `cpu_features`, `dynamic_n_ctx_max` 필드 연동 in `model_gateway/src/api/routes/inference_api.py`

**Checkpoint**: User Story 1 (MVP) 완결 ➔ 6대 CPU-GPU 자율 서빙 엔진 정상 작동

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

## Phase 5: User Story 3 (Priority: P3) - 설정 덮어쓰기(Anti-Shadowing) 방어 및 OOM 리소스 누수 격리

**Goal**: 함수 기본 인자(4096)에 의한 덮어쓰기를 차단하고, 좀비 프로세스 VRAM 누수 및 로딩 중 Cascade Kill 방어

**Independent Test**: 다중 동시 추론 및 프로세스 재기동 시 VRAM 누수와 설정 변조가 0건인지 카오스 테스트로 검증

- [ ] T015 [P] [US3] `inference_api.py` 및 `llama_manager.py`에서 요청에 `n_ctx`가 생략된 경우 동적 활성 컨텍스트를 무변조 주입하도록 가드 강화 in `model_gateway/src/api/routes/inference_api.py`
- [ ] T016 [US3] `llama_manager.py`의 `LOADING` 상태 가드를 강화하여 중복 요청 시 기존 프로세스 종료 없이 `_wait_for_ready` 대기하도록 방어 in `model_gateway/src/core/llama_manager.py`
- [ ] T017 [US3] 서브프로세스 종료 시 소켓 바인딩 해제 확인 및 미종료 프로세스 `SIGKILL` 강제 회수 로직 구현 in `model_gateway/src/core/process_manager.py`

**Checkpoint**: User Story 3 완결 ➔ Anti-Shadowing 및 OOM 리소스 누수 원천 격리

---

## Phase 6: Polish & 전사 5대 종합 회귀 테스트 및 라이브 검증

**Purpose**: 전사 통합 회귀 검증 및 문서 동기화 완결

- [ ] T018 [P] Model Gateway 신규 단위/계약 테스트 전체 실행 및 100% 통과 확인 in `model_gateway/tests/`
- [ ] T019 전사 5대 종합 회귀 테스트 스위트([run_all_regression_tests.py](file:///c:/AISERVICE/bteam/tests/run_all_regression_tests.py)) 실행 및 100% 통과 확인 in `bteam/tests/run_all_regression_tests.py`
- [ ] T020 [quickstart.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/quickstart.md)에 실시간 실행 로그 및 6대 CPU-GPU 하드웨어 실측 지표 기록 완료 in `specs/034-audit-config-oom-guards/quickstart.md`

---

## Dependencies & User Story Completion Order

```mermaid
flowchart TD
    Setup[Phase 1: Setup & 6-Tier Hardware Specs Setup] --> Foundational[Phase 2: Foundational & TDD Tests]
    Foundational --> US1[Phase 3: US1 - 6대 CPU-GPU 자율 서빙 엔진 (MVP)]
    US1 --> US2[Phase 4: US2 - 전사 레거시 하드코딩 제거]
    US2 --> US3[Phase 5: US3 - Anti-Shadowing & OOM 방어]
    US3 --> Polish[Phase 6: 전사 5대 회귀 테스트 & 검증 완결]
```
