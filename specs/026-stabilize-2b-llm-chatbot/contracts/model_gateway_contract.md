# Contract: Model Gateway Interface (026-stabilize-2b-llm-chatbot)

## Endpoint: `POST /v1/chat/completions`

### Request (Single Model Mode)
```json
{
  "model": "qwen3.5-2b",
  "messages": [
    {
      "role": "system",
      "content": "당신은 올리브영 뷰티 전문 가이드 AI입니다."
    },
    {
      "role": "user",
      "content": "여름철 모공 케어 수분크림 추천해줘"
    }
  ],
  "max_tokens": 2048,
  "temperature": 0.3,
  "stream": true
}
```

### Behavior in `SINGLE_MODEL_MODE=true`
1. 클라이언트가 `model: "qwen3.5-4b"` 또는 `model: "qwen3.5-9b"`를 요청하더라도, 게이트웨이는 기존 프로세스를 죽이지 않고 내부적으로 상주 중인 `qwen3.5-2b`로 매핑하여 즉시 서빙한다.
2. 응답 헤더 및 청크 스트림이 중단 없이 클라이언트로 전달된다.

### Response SSE Stream Chunk
```text
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1787155287,"model":"qwen3.5-2b","choices":[{"index":0,"delta":{"content":"안녕하세요!"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1787155287,"model":"qwen3.5-2b","choices":[{"index":0,"delta":{"content":" 여름철"},"finish_reason":null}]}

data: [DONE]
```
