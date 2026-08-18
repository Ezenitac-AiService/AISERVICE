# Interface Contract: Model Gateway (OpenAI Compatible)

---

## 1. 개요
통합 AI 모델 게이트웨이(`vllm-serv-gateway`)가 제공하는 표준 OpenAI 호환 추론 및 임베딩/리랭커 API 계약서이다.

---

## 2. API Endpoints

### 2.1 Chat Completions (`POST /v1/chat/completions`)
- **Port**: `8081` (또는 내부 프록시 `8089`)
- **Headers**:
  - `Content-Type: application/json`
  - `Authorization: Bearer EMPTY` (Optional)

#### Request Body
```json
{
  "model": "qwen3.5-4b",
  "messages": [
    {"role": "system", "content": "당신은 금융 및 뷰티 AI 어시스턴트입니다."},
    {"role": "user", "content": "PILOS 분석 결과 해석 방법"}
  ],
  "stream": true,
  "temperature": 0.3,
  "max_tokens": 1024
}
```

#### Response Body (Stream: false)
```json
{
  "id": "chatcmpl-010-refactor",
  "object": "chat.completion",
  "created": 1755489600,
  "model": "qwen3.5-4b",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "PILOS 감정 지수는 -1.0부터 +1.0 사이의 값으로..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 35,
    "completion_tokens": 120,
    "total_tokens": 155
  }
}
```

#### Response Body (Stream: true - SSE)
```text
data: {"id":"chatcmpl-010","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}
data: {"id":"chatcmpl-010","choices":[{"index":0,"delta":{"content":"PILOS"},"finish_reason":null}]}
...
data: [DONE]
```

---

### 2.2 Vector Embeddings (`POST /v1/embeddings`)
- **Port**: `8090`
- **Request Body**:
```json
{
  "model": "bge-m3",
  "input": ["차앤박 프로폴리스 앰플 수분감 분석"]
}
```
- **Response Body**:
```json
{
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "index": 0,
      "embedding": [0.0123, -0.0456, "... (1024차원 float) ..."]
    }
  ],
  "model": "bge-m3",
  "usage": {
    "prompt_tokens": 12,
    "total_tokens": 12
  }
}
```

---

### 2.3 Reranker (`POST /v1/rerank`)
- **Port**: `8091`
- **Request Body**:
```json
{
  "model": "bge-reranker-v2-m3",
  "query": "보습력이 뛰어난 에센스 추천",
  "documents": [
    "차앤박 프로폴리스 앰플은 강력한 보습막을 형성합니다.",
    "선크림은 자외선을 차단합니다."
  ],
  "top_n": 2
}
```
- **Response Body**:
```json
{
  "model": "bge-reranker-v2-m3",
  "results": [
    {"index": 0, "relevance_score": 0.954},
    {"index": 1, "relevance_score": 0.082}
  ]
}
```
