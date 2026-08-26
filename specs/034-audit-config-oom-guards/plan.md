# Implementation Plan: Audit, Zero-Hardcoding, and Hardware-Tiered Dynamic Context OOM Hardening

**Branch**: `034-audit-config-oom-guards` | **Date**: 2026-08-26 | **Spec**: [spec.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/spec.md)

**Input**: Feature specification from `specs/034-audit-config-oom-guards/spec.md`

---

## 1. Summary

본 계획서는 전사 코드베이스(`model_gateway`, `bteam/oliview_core`, `ateam/pilos`, `tests/`)에 산재한 레거시 하드코딩과 설정 덮어쓰기를 전수 제거하고, **물리 VRAM 실측에 기반한 동적 컨텍스트 윈도우 사이징 엔진(16K $\rightarrow$ 32K $\rightarrow$ 64K $\rightarrow$ 128K)** 및 **하드웨어 인식 FlashAttention/Pascal Q8 KV 최적화**, **11GB/12GB 4B 준비 및 8GB 2B 안전 상주 듀얼 아키텍처**를 완벽하게 구축하는 기술 구현 계획을 수립합니다.

---

## 2. Technical Context

* **언어 및 런타임**: Python 3.11 / 3.12, FastAPI, llama.cpp Python C-API (llama-server), CUDA 12.x
* **핵심 의존성**: `pynvml`, `httpx`, `pydantic v2`, `starlette`, `redis`
* **타겟 하드웨어**: NVIDIA GTX 1070 (8GB VRAM, Compute Capability 6.1, Pascal) + 11GB(1080Ti)/12GB(3060) 확장 대비
* **핵심 제약사항**:
  - Windows OS/데스크톱 UI 점유(~3.7GB)를 감안하여 전체 Gateway GPU 점유량을 **3.7GB 이하**로 통제.
  - Pascal SM 6.1 특성에 맞춰 `--flash_attn` 옵션은 생략하고 **Q8_0 KV Cache 양자화**로 VRAM 50% 절감.
  - 전사 회귀 테스트 스위트 100% 통과 유지.

---

## 3. Constitution Check

* **Principle I (언어 정책)**: 모든 기술 계획, 명세서, 주석, 가이드는 한국어로 작성 (통과 ✅).
* **Principle II (TDD 및 테스트 우선주의)**: 계약 및 단위 테스트 코드 선행 작성 후 구현 (통과 ✅).
* **Principle III (서비스 모듈화 및 격리)**: Model Gateway, A-Team, B-Team의 런타임 환경과 의존성 격리 유지 (통과 ✅).
* **Principle IV (관측 가능성 및 로깅)**: `GET /v1/profile` 및 구조화된 JSON 로깅 완비 (통과 ✅).
* **Principle V (단순성 및 점진적 진화 - YAGNI)**: 복잡한 외부 오케스트레이터 없이 단일 진실 소스(`ConfigManager`)와 수식 기반 자율 프로파일링 채택 (통과 ✅).

---

## 4. Phase 0 & Phase 1 Artifacts (Design)

* **Research**: [research.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/research.md)
* **Data Model**: [data-model.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/data-model.md)
* **Contracts**: [contracts/audit_integrity_contract.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/contracts/audit_integrity_contract.md)
* **Quickstart**: [quickstart.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/quickstart.md)

---

## 5. Technical Implementation Steps

### Step 1: `gpu_detector.py` 및 동적 사이징 엔진 구축
* Compute Capability 조회 및 `supports_flash_attn` 불리언 반환 로직 탑재.
* VRAM 기반 동적 컨텍스트 윈도우 수식 구현 (`calculate_dynamic_context_window()`).

### Step 2: `llama_manager.py` 및 `process_manager.py` 하드코딩 제거 & Pascal Q8 최적화
* SM < 8.0 환경에서 `--flash_attn` 옵션 자동 생략 및 `--cache-type-k q8_0 --cache-type-v q8_0` 주입.
* `LOADING` 상태 보호 및 `SIGTERM -> SIGKILL` 소켓 반환 검증 가드 탑재.

### Step 3: `inference_api.py` 및 `ConfigManager` 단일 진실 소스화
* `/v1/profile` 엔드포인트에 `hardware` 및 `dynamic_n_ctx_max` 필드 추가.
* 하드코딩된 fallback 문자열(`qwen3.5-4b`)을 `ConfigManager.get_default_model()`로 일원화.

### Step 4: A-Team (`ateam/pilos`) 및 B-Team (`bteam/oliview_core`) 설정 동기화
* `ateam/scripts/test_llm_connection.py` 및 레거시 계약 테스트 파일 전수 수정.
* `bteam/oliview_core/client.py` 및 `synthesis_node.py`의 동적 프로파일 바인딩 검증.

### Step 5: 전사 5대 종합 회귀 테스트 및 검증
* `bteam/tests/run_all_regression_tests.py` 100% 통과 확인.
