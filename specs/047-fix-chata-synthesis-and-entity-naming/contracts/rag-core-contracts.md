# RAG Core & Stream Contracts: 047-fix-chata-synthesis-and-entity-naming

## 1. Chat Stream SSE Protocol (`POST /api/v1/chat/stream`)

### Request Payload (`ChatStreamRequest`)
```json
{
  "query": "스킨케어에서 수분감 좋은 인기 앰플 추천해줘",
  "session_id": "session_live_001",
  "category_hint": "스킨케어",
  "bypass_cache": false
}
```

### Response Event Stream (`text/event-stream`)

#### Step Update Event (`event: step_update`)
```json
{
  "trace_id": "req_12345678",
  "event_type": "step_update",
  "step_id": "INTENT",
  "step_name": "1. 의도 및 대화 맥락 분석 중...",
  "status": "running",
  "timestamp": 1788338000.123
}
```

#### Token Chunk Event (`event: token`)
```json
{
  "trace_id": "req_12345678",
  "event_type": "token",
  "token": "스킨케어에서 수분감으로 많은 사랑을 받는 추천 제품은 다음과 같습니다.\n\n### 🌿 1. 차앤박(CNP) 뮤제너 피토 수딩 앰플\n- **수분감 및 진정 효과**: 피부 진정과 깊은 보습을 채워주는 앰플로 건조한 피부에 촉촉하게 스며듭니다 [차앤박 뮤제너 앰플 리뷰 1].",
  "timestamp": 1788338002.456
}
```

#### Stream Completion Event (`event: complete`)
```json
{
  "trace_id": "req_12345678",
  "event_type": "complete",
  "total_latency_sec": 3.45,
  "is_cached": false,
  "context_tier": "16K_BASELINE",
  "l5_cache_key": "chata:l5:hash123",
  "selected_review_count": 2,
  "reference_reviews": [
    {
      "rank": 1,
      "tag": "[차앤박 뮤제너 앰플 리뷰 1]",
      "product_name": "차앤박(CNP) 뮤제너 피토 수딩 앰플 35ml 1+1 기획",
      "clean_product_name": "차앤박 뮤제너 피토 수딩 앰플",
      "brand_name": "차앤박",
      "category": "스킨케어",
      "attribute_name": "수분감",
      "review_score": 5.0,
      "clean_text": "피부 진정과 수분을 채우는데 도움이 되는 앰플이어서 건조할 때마다 덧바르기 좋습니다.",
      "rerank_score": 0.9654,
      "product_url": "https://www.oliveyoung.co.kr/store/search/getSearchMain.do?query=%EC%B0%A8%EC%5B%B0%EB%B0%95%20%EB%AE%A4%EC%A0%9C%EB%84%88%20%ED%94%BC%ED%86%A0%20%EC%88%98%EB%94%A9%20%EC%95%B0%ED%94%8C",
      "oliveyoung_search_url": "https://www.oliveyoung.co.kr/store/search/getSearchMain.do?query=%EC%B0%A8%EC%5B%B0%EB%B0%95%20%EB%AE%A4%EC%A0%9C%EB%84%88%20%ED%94%BC%ED%86%A0%20%EC%88%98%EB%94%A9%20%EC%95%B0%ED%94%8C"
    }
  ],
  "metrics": {
    "total_latency_ms": 3450.0,
    "is_cached": false
  }
}
```

---

## 2. Python Core Interface Contracts (`bteam/oliview_core`)

### `MultiTargetGraphOrchestrator.stream_rag()`
```python
def stream_rag(
    self,
    query: str,
    session_id: str = "",
    tenant_id: str = "chata",
    bypass_cache: bool = False,
    category_hint: Optional[str] = None,
) -> Iterator[Dict[str, Any]]:
    """실시간 LangGraph RAG 파이프라인을 실행하고 단계별 SSE 이벤트를 스트리밍 방출합니다.

    Yields:
        Dict[str, Any]: SSE 이벤트 딕셔너리 (step_update, token, complete, error 등)
    """
```

### `AiGatewayClient.generate_stream()`
```python
def generate_stream(
    self,
    prompt: str,
    system_prompt: str = "당신은 올리브영 뷰티 리뷰 분석 AI 어시스턴트 '올리뷰'입니다.",
    max_tokens: int = 4096,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    repetition_penalty: Optional[float] = None,
    trace_id: str = "",
    tenant_id: str = "default",
    session_id: str = "",
    queue_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Iterator[str]:
    """vLLM 모델 서빙 게이트웨이에 SSE 스트리밍 요청을 전송하고 실시간 생성 토큰을 반환합니다.

    Timeout:
        inactivity_timeout_s (180.0초) 슬라이딩 유휴 타임아웃 적용.
    """
```
