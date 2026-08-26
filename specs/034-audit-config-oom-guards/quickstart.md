# Quickstart & Verification Guide: Hardware-Tiered Dynamic Context & OOM Hardening

**Feature**: `034-audit-config-oom-guards`  
**Date**: 2026-08-26  
**Status**: Verified & Production Ready (100% Pass)

---

## 1. 사전 조건 (Prerequisites)
* Docker 컨테이너 가동: `vllm-serv-gateway`, `oliview_chatbot_b`, `aiservice-redis`
* GPU: NVIDIA GTX 1070 (8GB VRAM, Pascal SM 6.1) / Ampere / Ada / Blackwell 호환
* Host CPU: AVX/AVX2 독립 실측

---

## 2. 검증 시나리오 및 실측 결과 (Verification Scenarios & Results)

### 시나리오 1: 전사 레거시 하드코딩 전수 감사 (Static Audit)
```bash
python model_gateway/scripts/scan_hardcoding.py
```
**실측 결과**:
```text
================================================================================
AISERVICE Static Hardcoding & Config Shadowing Scanner
================================================================================
Scan Complete: Scanned 12011 files.
[PASS] 0 hardcoding or shadowing violations detected!
```

### 시나리오 2: 3대 직교 하드웨어 프로파일 및 FlashAttention Pascal SM 6.1 최적화 확인
```bash
curl -s http://127.0.0.1:8081/v1/profile
```
**실측 결과**:
```json
{
  "status": "healthy",
  "active_model": "qwen3.5-2b",
  "current_n_ctx": 16384,
  "dynamic_n_ctx_max": 32768,
  "hardware": {
    "device_name": "NVIDIA GeForce GTX 1070",
    "compute_capability": 6.1,
    "gpu_features": {
      "architecture_name": "Pascal",
      "compute_capability": 6.1,
      "has_tensor_cores": false,
      "supports_fp16_native": false,
      "supports_bf16_native": false,
      "supports_fp8_native": false,
      "supports_fp4_native": false,
      "supports_flash_attn": false,
      "recommended_kv_type": "q8_0"
    },
    "cpu_features": {
      "cpu_model_name": "Intel(R) Xeon(R) CPU E5-2680 v4 @ 2.40GHz",
      "has_avx": true,
      "has_avx2": true,
      "has_fma": true,
      "requires_gpu_only": false
    },
    "total_vram_mb": 8192,
    "free_vram_mb": 6863,
    "recommended_model": "qwen3.5-2b",
    "dynamic_n_ctx": 32768,
    "use_q8_kv": true,
    "use_fp8_kv": false,
    "use_fp4_kv": false,
    "use_flash_attn": false,
    "force_all_gpu_layers": false
  },
  "vram_total_mb": 8192,
  "vram_used_mb": 1329,
  "single_model_mode": true
}
```

### 시나리오 3: 3대 직교 단위 및 플래그 TDD 테스트
```bash
docker compose exec -T vllm-serv pytest tests/test_gpu_architecture_specs.py tests/test_hardware_aware_flags.py tests/test_config_hierarchy.py
```
**실측 결과**:
```text
======================== 6 passed, 3 warnings in 1.19s =========================
```

### 시나리오 4: 전사 5대 종합 회귀 테스트 스위트 (Oliview Core)
```bash
docker compose exec -T oliview_chatbot_b python tests/run_all_regression_tests.py
```
**실측 결과**:
```text
================================================================
   🧪 OLIVIEW CORE COMPREHENSIVE REGRESSION TEST SUITE 🧪   
================================================================
[1/5] Security & Prompt Injection Guardrails Regression (Spec 021 / 022)...
  ✅ Security & Guardrails: 3/3 Tests Passed!
[2/5] Intent Router & Pattern Classification Regression (Spec 030)...
  ✅ Intent Router: 2/2 Tests Passed!
[3/5] L5 Caching & SingleFlight Lock Regression (Spec 032)...
  ✅ L5 Core & SingleFlight: 4/4 Tests Passed!
[4/5] Word-Boundary Replay Stream Fidelity Regression (Spec 032)...
  ✅ Word-Boundary Replay: 15 Chunks Emitted with 100% Fidelity!
[5/5] E2E RAG Pipeline Cold -> Warm L5 Cache Hit Regression (Spec 032)...
  ✅ E2E L5 RAG Cache: Warm TTFT <50ms, is_cached=True (100% Match) Passed!
================================================================
   🎉 ALL 5 REGRESSION TEST SUITES PASSED (100% SUCCESS) 🎉   
================================================================
```
