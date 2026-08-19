# API Contract: Model Gateway Routing & Fallback

**Contract Version**: 1.0.0  
**Feature**: `013-tiered-llm-model-routing`  
**Endpoint**: `POST /v1/chat/completions`

---

## 1. 개요 (Overview)
클라이언트(A팀 리포트/챗봇, B팀 OllyChat/RAG)가 `vllm-serv-gateway:8081`에 OpenAI 호환 요청을 전송할 때의 라우팅 규격, 우선순위 태깅 및 2B 무중단 Fallback 처리 계약입니다.

---

## 2. 요청 사양 (Request Specification)

### 2.1 헤더 (Headers)
```http
Content-Type: application/json
Accept: application/json (또는 text/event-stream)
```

### 2.2 요청 본문 (Request Body)
```json
{
  "model": "qwen3.5-4b",
  "priority": "high",
  "messages": [
    {
      "role": "system",
      "content": "당신은 화장품 추천 전문 어시스턴트입니다."
    },
    {
      "role": "user",
      "content": "민감성 피부에 좋은 수분 크림 리뷰 비교해줘."
    }
  ],
  "temperature": 0.3,
  "max_tokens": 1024,
  "response_format": {
    "type": "text"
  },
  "stream": false
}
```

---

## 3. 응답 사양 (Response Specification)

### 3.1 정상 응답 (HTTP 200 OK - 4B 성공)
```json
{
  "id": "chatcmpl-tiered-4b-101",
  "object": "chat.completion",
  "created": 1724050000,
  "model": "qwen3.5-4b",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "민감성 피부를 위한 주요 수분 크림 3종의 리뷰를 비교해 드립니다..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 340,
    "completion_tokens": 180,
    "total_tokens": 520
  }
}
```

### 3.2 4B 오류 시 2B 자동 Fallback 응답 (HTTP 200 OK - 헤더/메타데이터에 Fallback 명시)
4B 모델 로드 실패나 타임아웃 발생 시 클라이언트에 에러를 던지지 않고 2B 모델이 즉시 답변을 합성합니다.

```json
{
  "id": "chatcmpl-tiered-2b-fallback-102",
  "object": "chat.completion",
  "created": 1724050002,
  "model": "qwen3.5-2b",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "민감성 피부에 적합한 수분 크림들의 리뷰 특징을 안내해 드립니다..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 340,
    "completion_tokens": 150,
    "total_tokens": 490
  }
}
```
- **특수 응답 헤더**: `X-Model-Fallback: true`, `X-Fallback-Reason: "4B_TIMEOUT_OR_VRAM_LIMIT"`
