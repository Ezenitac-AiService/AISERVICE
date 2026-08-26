# Implementation Plan: Audit, Zero-Hardcoding, and 5-Tier GPU Architecture OOM Hardening

**Branch**: `034-audit-config-oom-guards` | **Date**: 2026-08-26 | **Spec**: [spec.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/spec.md)

**Input**: Feature specification from `specs/034-audit-config-oom-guards/spec.md`

---

## 1. Summary

본 계획서는 5대 타겟 GPU 세대(GTX 1070 8GB, GTX 1080Ti 11GB, RTX 2080 8GB, RTX 3060 12GB, RTX 4080 16GB)별 불변 하드웨어 특성 룩업 테이블(`GPU_ARCHITECTURE_SPEC_TABLE`)을 구축하고, Host CPU(Intel i7 930)의 AVX 미지원 특성을 고려한 **100% GPU VRAM 상주 (`-ngl 999`) 원칙**과 **물리 VRAM 실측 기반 동적 컨텍스트 사이징 엔진(16K $\rightarrow$ 32K $\rightarrow$ 64K $\rightarrow$ 128K)**을 완성합니다.  
동시에 전사 코드베이스(`model_gateway`, `bteam/oliview_core`, `ateam/pilos`, `tests/`)에 산재한 레거시 하드코딩을 `ConfigManager`로 완전 일원화합니다.

---

## 2. Technical Context

* **호스트 CPU**: Intel Core i7 930 (1세대 Nehalem, SSE4.2 지원, **AVX/AVX2/AVX-512 미지원**) $\rightarrow$ 모든 신경망 연산 100% GPU VRAM Offload 필수.
* **5대 GPU 타겟**:
  - **Pascal (SM 6.1)**: GTX 1070 (8GB), GTX 1080Ti (11GB) $\rightarrow$ FlashAttn 생략, Q8_0 KV Cache 필수.
  - **Turing (SM 7.5)**: RTX 2080 (8GB) $\rightarrow$ FP16 텐서 코어, Q8_0 KV Cache.
  - **Ampere (SM 8.6)**: RTX 3060 (12GB) $\rightarrow$ BF16 / FlashAttention-2/3 완전 지원, 4B @ 64K.
  - **Ada Lovelace (SM 8.9)**: RTX 4080 (16GB) $\rightarrow$ FP8 Transformer Engine / FlashAttention-3 완전 지원, 4B @ 128K / 9B @ 32K.
* **소프트웨어 스택**: Python 3.11 / 3.12, FastAPI, llama.cpp Python C-API, CUDA 12.x, PyNVML, Pydantic v2.

---

## 3. Constitution Check

* **Principle I ~ V 100% 충족**: 한국어 문서화, TDD 선행, 서비스 모듈화, 구조화 로깅, YAGNI 원칙 준수.

---

## 4. Phase 0 & Phase 1 Artifacts (Design)

* **Research**: [research.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/research.md)
* **Data Model**: [data-model.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/data-model.md)
* **Contracts**: [contracts/audit_integrity_contract.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/contracts/audit_integrity_contract.md)
* **Quickstart**: [quickstart.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/quickstart.md)

---

## 5. Technical Implementation Steps

### Step 1: 5대 GPU 세대별 불변 스펙 룩업 테이블 및 감지 엔진 구축
* `gpu_detector.py`에 `GPU_ARCHITECTURE_SPEC_TABLE` 정의 및 `detect_gpu_capabilities()` 구현.
* VRAM 물리 수식 기반 `calculate_dynamic_context_window(vram_total_mb)` 구현.

### Step 2: `process_manager.py` 세대별 최적 플래그 자동 주입
* SM 6.1/7.5: `--flash_attn` 생략, `--cache-type-k q8_0 --cache-type-v q8_0` 주입.
* SM 8.6/8.9: `--flash_attn True`, FP8/Q8 KV 자동 주입.
* 모든 모델에 `-ngl 999` 강제 적용 (i7 930 CPU 오프로드 방지).

### Step 3: `llama_manager.py` 및 `inference_api.py` 전사 하드코딩 제거
* `ConfigManager`로 레거시 fallback 문자열(`qwen3.5-4b`) 전수 교체.
* `GET /v1/profile`에 `architecture` 및 `features` 메타데이터 노출.

### Step 4: `ateam/pilos` 및 전사 테스트 스위트 동기화
* `ateam/scripts/test_llm_connection.py` 및 레거시 계약 테스트 파일 전수 교체.

### Step 5: 전사 5대 종합 회귀 테스트 및 검증
* `bteam/tests/run_all_regression_tests.py` 100% 통과 확인.
