# Contract: Model Gateway HTTP API Specifications

**Component**: `vllm-serv-gateway`  
**Network**: `aiservice-network` (Internal Only)  
**Spec Reference**: [spec.md](file:///c:/AISERVICE/specs/002-public-domain-duckdns-gateway/spec.md) (FR-005, FR-006)

---

## 1. Endpoints & Ports

| Service Type | Hostname & Port | Endpoint | Protocol | Model |
|---|---|---|---|---|
| **Chat LLM (Multi-Tier)** | `http://vllm-serv-gateway:8081` | `/v1/chat/completions` | HTTP POST (SSE Stream) | `qwen3.5-4b` / `qwen3.5-2b` |
| **Embedding** | `http://vllm-serv-gateway:8090` | `/v1/embeddings` | HTTP POST | `bge-m3` |
| **Reranker** | `http://vllm-serv-gateway:8091` | `/v1/rerank` (or `/rerank`) | HTTP POST | `bge-reranker-v2-m3` |

---

## 2. Embedding Contract (`POST /v1/embeddings`)

### Request
```json
{
  "model": "bge-m3",
  "input": "진정 효과가 뛰어난 티트리 세럼 추천해줘" // or string array: ["문장 1", "문장 2"]
}
```

### Response
```json
{
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "index": 0,
      "embedding": [-0.0234, 0.0512, ..., 0.0198]
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

## 3. Chat Completion Contract (`POST /v1/chat/completions`)

### Request
```json
{
  "model": "qwen3.5-4b",
  "messages": [
    {"role": "system", "content": "당신은 올리브영 뷰티 전문 AI 상담원입니다."},
    {"role": "user", "content": "피부 진정 앰플 추천해줘"}
  ],
  "temperature": 0.3,
  "max_tokens": 4096,
  "stream": true
}
```

### Response (SSE Stream)
```text
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"브링그린"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":" 징크테카 트러블 세럼을 추천드립니다."},"finish_reason":"stop"}]}

data: [DONE]
```
