# Contract: Dynamic Hardware Profile & Zero-Hardcoding Integrity API

**Feature**: `034-audit-config-oom-guards`  
**Date**: 2026-08-26  
**Status**: Active Contract

---

## 1. `GET /v1/profile` (하드웨어 프로파일 및 동적 컨텍스트 조회 API)

### 요청
* **Method**: `GET`
* **Path**: `/v1/profile`

### 응답 규격 (JSON)
```json
{
  "status": "healthy",
  "active_model": "qwen3.5-2b",
  "current_n_ctx": 16384,
  "dynamic_n_ctx_max": 32768,
  "hardware": {
    "device_name": "NVIDIA GeForce GTX 1070",
    "compute_capability": 6.1,
    "supports_flash_attn": false,
    "use_q8_kv": true,
    "hardware_tier": "tier_1_8gb",
    "vram_total_mb": 8192,
    "vram_used_mb": 3708,
    "vram_free_mb": 4484
  },
  "single_model_mode": true
}
```

---

## 2. `POST /v1/chat/completions` (동적 컨텍스트 & 무변조 투명 라우팅 계약)

### 요청 헤더 및 페이로드
```json
{
  "model": "qwen3.5-4b",
  "messages": [
    {"role": "user", "content": "차앤박 앰플 분석해줘"}
  ],
  "stream": true
}
```

### 동작 및 응답 규격
1. **8GB 환경 (`single_model_mode: true`)**:
   - `qwen3.5-4b` 요청 유입 시 프로세스 재시작 없이 상주 중인 `qwen3.5-2b`로 투명 매핑.
   - 응답 헤더: `x-model-served: qwen3.5-2b`.
   - `HTTP 200 OK` 및 SSE 스트리밍 정상 완결.
2. **11GB/12GB+ 환경 (`single_model_mode: false`)**:
   - 4B 모델로 직접 서빙.
   - 응답 헤더: `x-model-served: qwen3.5-4b`.
