# Contract: Model Gateway Concurrency & Embedding API Contract (009-fix-ollychat-embedding-timeout)

## 1. Embedding Endpoint (`POST /v1/embeddings`)

- **Host**: `http://vllm-serv-gateway:8090` (또는 메인 게이트웨이 `8081` 라우트)
- **Method**: `POST`
- **Path**: `/v1/embeddings`
- **Content-Type**: `application/json`

### Request Payload
```json
{
  "model": "bge-m3",
  "input": ["차앤박 프로폴리스 앰플 수분감을 분석해줘"]
}
```

### Response (200 OK)
```json
{
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "index": 0,
      "embedding": [0.0123, -0.0456, 0.0789, "... (1024 floats)"]
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

## 2. LLM Streaming with Keep-Alive Queue (`POST /v1/chat/completions`)

- **Host**: `http://vllm-serv-gateway:8081`
- **Method**: `POST`
- **Path**: `/v1/chat/completions`
- **Content-Type**: `application/json`

### SSE Event Stream Sequence when Queued

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive

data: {"type": "status", "content": "LLM 서버가 다른 질문을 처리 중입니다. 순서를 기다리고 있습니다...", "queue_position": 1}

data: {"type": "token", "content": "차앤박 "}

data: {"type": "token", "content": "프로폴리스 "}

data: {"type": "token", "content": "앰플의 "}

data: {"type": "done", "status": "ready"}

data: [DONE]
```
