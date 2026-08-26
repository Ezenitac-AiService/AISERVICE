# Interface Contract: Queue SSE Protocol & Client Cancellation

**Feature**: `031-gpu-queue-timeout-extension`  
**Date**: 2026-08-26  
**Status**: Approved  

---

## 1. Gateway Inference SSE Streaming Contract (`POST /v1/chat/completions`)

### 1.1 Request Headers
```http
POST /v1/chat/completions HTTP/1.1
Host: 127.0.0.1:8081
Accept: text/event-stream
Content-Type: application/json
X-Tenant-Id: chata
X-Session-Id: ses_12345678
Idempotency-Key: idm_8af43ba19c2e
```

### 1.2 SSE Event Progression Lifecycle

#### Phase 1: 큐 진입 직후 (Immediate Response, <200ms)
```sse
event: queue_status
data: {"ticket_id":"req_8af43ba1","tenant_id":"chata","status":"QUEUED","queue_position":1,"total_queued":2,"active_slots":1,"max_slots":1,"estimated_wait_sec":4.0,"timestamp":1724670000.100}

```

#### Phase 2: 대기 중 순번 갱신 (Event-Driven / 3~5s Periodic)
```sse
event: queue_status
data: {"ticket_id":"req_8af43ba1","tenant_id":"chata","status":"QUEUED","queue_position":1,"total_queued":1,"active_slots":1,"max_slots":1,"estimated_wait_sec":1.5,"timestamp":1724670003.500}

```

#### Phase 3: 무응답 방지 Keep-Alive (15s Periodic)
```sse
: keepalive

```

#### Phase 4: GPU 슬롯 획득 및 추론 시작 (Active Transition)
```sse
event: queue_status
data: {"ticket_id":"req_8af43ba1","tenant_id":"chata","status":"ACTIVE","queue_position":0,"active_slots":1,"max_slots":1,"timestamp":1724670005.000}

event: message
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1724670005,"model":"qwen3.5-2b","choices":[{"index":0,"delta":{"content":"안녕"},"finish_reason":null}]}

event: message
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1724670005,"model":"qwen3.5-2b","choices":[{"index":0,"delta":{"content":"하세요!"},"finish_reason":null}]}

event: message
data: [DONE]

```

---

## 2. Cancellation API (`POST /v1/queue/cancel`)

대기 중인 요청을 명시적으로 취소할 때 호출하는 엔드포인트입니다.

### Request
```http
POST /v1/queue/cancel HTTP/1.1
Host: 127.0.0.1:8081
Content-Type: application/json

{
  "ticket_id": "req_8af43ba1",
  "session_id": "ses_12345678"
}
```

### Response
```json
{
  "status": "CANCELLED",
  "ticket_id": "req_8af43ba1",
  "message": "Request successfully purged from GPU queue."
}
```
