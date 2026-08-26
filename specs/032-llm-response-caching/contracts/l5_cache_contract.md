# Interface & Schema Contract: 032-llm-response-caching

**Feature**: `032-llm-response-caching`  
**Date**: 2026-08-26  
**Status**: Ready  

---

## 1. Redis Key & Data Storage Contract

### Key Pattern
```
olliview:l5:{tenant_id}:{hash_32}
```

* `tenant_id`: `chata` (Streamlit) 또는 `chatb` (Web UI/API)
* `hash_32`: `SHA256(NFKC(rewritten_query) + doc_ids_hash + prompt_version + model_id)[:32]`

### TTL Specification
* Base TTL: `43,200` seconds (12 hours)
* Jitter Window: `±3,600` seconds (±1 hour)
* Effective TTL Range: `39,600 ~ 46,800` seconds

### Stored JSON Payload Schema
```json
{
  "response_text": "### 🌿 차앤박 프로폴리스 에너지 액티브 앰플 분석 결과\n\n- **주요 효능**: 고농축 프로폴리스 추출물이 함유되어 지친 피부에 풍부한 영양과 꿀광 보습을 공급합니다.\n- **사용감 및 제형**: 끈적임 없이 쫀쫀하게 밀착 흡수되어 메이크업 전 속건조 개선에 탁월합니다.",
  "model_id": "qwen3.5-2b",
  "prompt_version": "v1.0",
  "tenant_id": "chata",
  "doc_ids_hash": "a8f3b9c201d4e7f8",
  "created_at": 1787719200.123,
  "estimated_tokens": 142
}
```

---

## 2. Streaming Cache Replay SSE Event Contract

캐시 히트 시 클라이언트에 스트리밍되는 SSE 청크 및 메타데이터 포맷:

### Event 1: Initial Cache Hit Metadata (Optional Event Header)
```http
event: cache_status
data: {"is_cached": true, "source": "redis_l5", "latency_saved_s": 5.42, "tenant_id": "chata"}

```

### Event 2: Word-Boundary Token Delta Stream (Identical to Standard OpenAI SSE Chunk)
```http
data: {"id": "chatcmpl-cached-7f9a1b", "object": "chat.completion.chunk", "created": 1787719200, "model": "qwen3.5-2b", "choices": [{"index": 0, "delta": {"content": "### 🌿 차앤박"}, "logprobs": null, "finish_reason": null}]}

data: {"id": "chatcmpl-cached-7f9a1b", "object": "chat.completion.chunk", "created": 1787719200, "model": "qwen3.5-2b", "choices": [{"index": 0, "delta": {"content": " 프로폴리스"}, "logprobs": null, "finish_reason": null}]}

data: {"id": "chatcmpl-cached-7f9a1b", "object": "chat.completion.chunk", "created": 1787719200, "model": "qwen3.5-2b", "choices": [{"index": 0, "delta": {"content": " 에너지"}, "logprobs": null, "finish_reason": null}]}

...

data: {"id": "chatcmpl-cached-7f9a1b", "object": "chat.completion.chunk", "created": 1787719200, "model": "qwen3.5-2b", "choices": [{"index": 0, "delta": {}, "logprobs": null, "finish_reason": "stop"}]}

data: [DONE]

```

---

## 3. Python Core Interface (`redis_pool.py` & `synthesis_node.py`)

### Helper Functions in `redis_pool.py`:
```python
def build_l5_key(
    tenant_id: str,
    rewritten_query: str,
    doc_ids: List[str],
    model_id: str = "qwen3.5-2b",
    prompt_version: str = "v1.0"
) -> str:
    """Spec 032 FR-001: L5 LLM 응답 캐시 키 생성."""
    ...

def get_l5_response(key: str) -> Optional[dict]:
    """Spec 032 FR-002: L5 캐시 조회 (Fail-Fast 0.2s)."""
    ...

def set_l5_response(key: str, payload: dict, ttl_base: int = 43200) -> bool:
    """Spec 032 FR-004/FR-005: Deny-list 검증 및 Jitter 포함 캐시 저장."""
    ...

async def replay_cached_stream(
    cached_payload: dict,
    chunk_delay_s: float = 0.025
) -> AsyncGenerator[str, None]:
    """Spec 032 FR-003: 단어 경계 단위 고속 스트리밍 Replay 제너레이터."""
    ...
```
