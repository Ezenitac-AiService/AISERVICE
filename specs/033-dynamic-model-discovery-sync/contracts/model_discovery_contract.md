# API & Interface Contract: Dynamic Model Discovery & Gateway Synchronization

**Feature**: `033-dynamic-model-discovery-sync`  
**Date**: 2026-08-26  
**Status**: Active Contract

---

## 1. Model Gateway Discovery Endpoints

### 1.1 `GET /v1/profile` (Hardware & Model Status)
게이트웨이의 GPU VRAM 현황과 상주 활성 모델 정보를 제공하는 엔드포인트입니다.

* **Method**: `GET`
* **URL**: `http://vllm-serv-gateway:8081/v1/profile`
* **Response Headers**: `Content-Type: application/json`
* **Response Status**: `200 OK`

```json
{
  "status": "healthy",
  "active_model": "qwen3.5-2b",
  "current_n_ctx": 16384,
  "vram_total_mb": 8192,
  "vram_used_mb": 5984,
  "single_model_mode": true,
  "models": [
    {
      "id": "qwen3.5-2b",
      "object": "model",
      "owned_by": "me",
      "is_active": true,
      "is_resident": true,
      "max_context_window": 34304,
      "vram_footprint_mb": 1500
    },
    {
      "id": "qwen3.5-4b",
      "object": "model",
      "owned_by": "me",
      "is_active": false,
      "is_resident": false,
      "max_context_window": 16384,
      "vram_footprint_mb": 2800
    }
  ]
}
```

---

### 1.2 `GET /v1/models` (OpenAI Compatible Catalog)
표준 OpenAI 카탈로그 형식에 활성 모델 메타데이터를 보강하여 제공합니다.

* **Method**: `GET`
* **URL**: `http://vllm-serv-gateway:8081/v1/models`
* **Response Status**: `200 OK`

```json
{
  "object": "list",
  "data": [
    {
      "id": "qwen3.5-2b",
      "object": "model",
      "owned_by": "me",
      "is_active": true,
      "current_n_ctx": 16384
    },
    {
      "id": "bge-m3",
      "object": "model",
      "owned_by": "me",
      "is_active": true
    },
    {
      "id": "bge-reranker-v2-m3",
      "object": "model",
      "owned_by": "me",
      "is_active": true
    }
  ]
}
```

---

## 2. Transparent Model Aliasing Contract (`POST /v1/chat/completions`)

* **Given**: `SINGLE_MODEL_MODE=true` 상태에서 게이트웨이에 `qwen3.5-2b (16K ctx)`가 상주 중.
* **When**: 클라이언트가 `{"model": "qwen3.5-4b", ...}` 또는 `{"model": "qwen3.5-9b", ...}`를 전송.
* **Then**:
  1. 게이트웨이는 프로세스 킬/스와핑을 시도하지 않는다.
  2. 게이트웨이 내부 프록시는 요청 본문의 `model` 필드를 현재 상주 중인 `"qwen3.5-2b"`로 즉시 치환한다.
  3. `200 OK`와 함께 스트리밍 SSE 토큰을 반환한다.
  4. 응답 헤더 `x-model-served: qwen3.5-2b`를 포함하여 실제 서비스된 모델을 투명하게 고지한다.

---

## 3. Client Discovery Contract (`AiGatewayClient`)

### `discover_active_model(force_refresh: bool = False) -> str`
* **동작**:
  1. 인메모리 `ModelDiscoveryCache`가 유효하고 `force_refresh=False`인 경우 즉시 캐시된 모델명(`qwen3.5-2b`) 반환 (0ms).
  2. 캐시 만료 시 게이트웨이 `GET /v1/models` 또는 `GET /v1/profile`을 1초 타임아웃으로 호출하여 `is_active=True`인 LLM 모델명 획득 후 캐시 갱신.
  3. 네트워크 오류나 타임아웃 발생 시 `CoreSettings.synthesis_llm_model`로 자동 폴백.
