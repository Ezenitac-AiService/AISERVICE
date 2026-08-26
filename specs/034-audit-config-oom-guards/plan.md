# Implementation Plan: Audit, Zero-Hardcoding, and Unified CPU-GPU Hardware Evaluation Checklist OOM Hardening

**Branch**: `034-audit-config-oom-guards` | **Date**: 2026-08-26 | **Spec**: [spec.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/spec.md)

**Input**: Feature specification from `specs/034-audit-config-oom-guards/spec.md`

---

## 1. Summary

본 계획서는 CPU와 GPU가 고정된 세트가 아니므로, **CPU(명령어 세트/AVX 유무)와 GPU(아키텍처/VRAM/텐서 코어)를 모두 통합적으로 고려하는 단일 하드웨어 평가 체크리스트**를 구축합니다.  
이를 통해 AVX 미지원 CPU(예: i7 930) 감지 시 **100% GPU VRAM 상주 (`-ngl 999`)**를 강제하고, 물리 VRAM 실측 기반 **동적 컨텍스트 사이징 엔진(16K $\rightarrow$ 32K $\rightarrow$ 64K $\rightarrow$ 128K)** 및 전사 하드코딩 제거를 완결합니다.

---

## 2. Technical Context

* **통합 하드웨어 평가 범위**:
  - **GPU 평가 (Pascal $\rightarrow$ Blackwell)**:
    - Pascal (SM 6.1): FlashAttn 생략, Q8_0 KV Cache 필수.
    - Turing (SM 7.5): FP16 텐서 코어, Q8_0 KV Cache.
    - Ampere (SM 8.6): FlashAttention-2/3 완전 지원, 4B @ 64K.
    - Ada Lovelace (SM 8.9): FP8 Transformer Engine / FlashAttention-3 완전 지원, 4B @ 128K / 9B @ 32K.
    - Blackwell (SM 12.0): FP4 NVFP4 / FlashAttention-4(TMA) 완전 지원, 4B @ 128K / 9B @ 64~128K.
  - **CPU 평가 (AVX 명령어 세트)**:
    - AVX 미지원 (i7 930 등): 100% GPU VRAM Offload (`-ngl 999`) 강제, CPU BLAS 연산 배제.
    - AVX2 지원 (현대적 Intel/AMD): 고속 토큰 직렬화 및 DMA 버퍼 파이프라인 활성화.
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

### Step 1: 통합 CPU & GPU 하드웨어 룩업 테이블 및 감지 엔진 구축
* `gpu_detector.py`에 `detect_hardware_capabilities()` 구현 (CPU AVX 실측 + GPU Pascal~Blackwell 매칭).
* VRAM 물리 수식 기반 `calculate_dynamic_context_window(vram_total_mb)` 구현.

### Step 2: `process_manager.py` 세대별 최적 플래그 자동 주입
* AVX 미지원 감지 시 `-ngl 999` 강제 적용 (CPU 연산 누수 원천 차단).
* SM 6.1/7.5: `--flash_attn` 생략, `--cache-type-k q8_0 --cache-type-v q8_0` 주입.
* SM 8.6/8.9/12.0: `--flash_attn True`, FP8/FP4/Q8 KV 자동 주입.

### Step 3: `llama_manager.py` 및 `inference_api.py` 전사 하드코딩 제거
* `ConfigManager`로 레거시 fallback 문자열(`qwen3.5-4b`) 전수 교체.
* `GET /v1/profile`에 `gpu_features`, `cpu_features`, `dynamic_n_ctx_max` 메타데이터 노출.

### Step 4: `ateam/pilos` 및 전사 테스트 스위트 동기화
* `ateam/scripts/test_llm_connection.py` 및 레거시 계약 테스트 파일 전수 교체.

### Step 5: 전사 5대 종합 회귀 테스트 및 검증
* `bteam/tests/run_all_regression_tests.py` 100% 통과 확인.
