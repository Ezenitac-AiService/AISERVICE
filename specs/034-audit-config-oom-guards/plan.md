# Implementation Plan: Audit, Zero-Hardcoding, and 3-Axis Decoupled Hardware Evaluation Engine OOM Hardening

**Branch**: `034-audit-config-oom-guards` | **Date**: 2026-08-26 | **Spec**: [spec.md](file:///c:/AISERVICE/specs/034-audit-config-oom-guards/spec.md)

**Input**: Feature specification from `specs/034-audit-config-oom-guards/spec.md`

---

## 1. Summary

본 계획서는 GPU 아키텍처(SM 6.1~12.0), 물리 VRAM 용량(8GB~24GB+), CPU 명령어 세트(AVX 유무)라는 **3대 직교 독립 변수를 런타임에 각각 실측하여 수학적으로 합성하는 하드웨어 감지 엔진**을 구축합니다.  
이를 통해 4/5세대 텐서 코어를 탑재한 8GB GPU(RTX 4060 8GB, RTX 5060 8GB) 등 모든 하드웨어 변종 조합에서도 FlashAttention-3/4와 FP8/FP4/Q8 KV 양자화, 동적 컨텍스트 사이징($n_{\text{ctx}}$: 16K~128K)이 100% 자율 구성됩니다.

---

## 2. Technical Context

* **3대 직교 독립 하드웨어 결정 축**:
  - **축 1 (GPU 아키텍처)**: Pascal(SM 6.1, Q8 KV) $\rightarrow$ Turing(SM 7.5, Q8 KV) $\rightarrow$ Ampere(SM 8.6, FA-2/3) $\rightarrow$ Ada(SM 8.9, FA-3/FP8) $\rightarrow$ Blackwell(SM 12.0, FA-4/FP4).
  - **축 2 (물리 VRAM 예산)**: 8GB(2B 상주, KV 타입에 따라 16K~128K), 11GB(4B @ 32K~48K), 12GB(4B @ 64K), 16GB(4B @ 128K / 9B @ 32~64K), 24GB+(9B @ 128K).
  - **축 3 (CPU 명령어 세트)**: AVX 미지원(i7 930 등) 감지 시 `-ngl 999` 100% GPU 강제, AVX2 지원 시 호스트 DMA 가속.
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

### Step 1: 3대 직교 하드웨어 룩업 테이블 및 감지 엔진 구축
* `gpu_detector.py`에 `detect_hardware_capabilities()` 구현 (CPU AVX 실측 + GPU SM 6.1~12.0 매칭 + 물리 VRAM 예산 수식 합성).
* VRAM 물리 수식 기반 `calculate_dynamic_context_window(vram_total_mb, kv_cache_type)` 구현.

### Step 2: `process_manager.py` 세대별 최적 플래그 자동 주입
* AVX 미지원 감지 시 `-ngl 999` 강제 적용.
* SM 6.1/7.5: `--flash_attn` 생략, `--cache-type-k q8_0 --cache-type-v q8_0` 주입.
* SM 8.6/8.9/12.0: `--flash_attn True`, FP8/FP4/Q8 KV 자동 주입.

### Step 3: `llama_manager.py` 및 `inference_api.py` 전사 하드코딩 제거
* `ConfigManager`로 레거시 fallback 문자열(`qwen3.5-4b`) 전수 교체.
* `GET /v1/profile`에 `gpu_features`, `cpu_features`, `dynamic_n_ctx_max` 메타데이터 노출.

### Step 4: `ateam/pilos` 및 전사 테스트 스위트 동기화
* `ateam/scripts/test_llm_connection.py` 및 레거시 계약 테스트 파일 전수 교체.

### Step 5: 전사 5대 종합 회귀 테스트 및 검증
* `bteam/tests/run_all_regression_tests.py` 100% 통과 확인.
