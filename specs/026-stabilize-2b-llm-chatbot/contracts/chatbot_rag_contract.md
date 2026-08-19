# Contract: Chatbot RAG Search & Stream Interface (026-stabilize-2b-llm-chatbot)

## 1. Chatbot B Stream Endpoint: `POST /api/v1/search/stream`

### Request Payload
```json
{
  "query": "여름철 기름기 잡고 모공 커버 잘되는 매트 쿠션 추천해줘",
  "brand": "이니스프리",
  "top_k": 20,
  "top_n": 3,
  "max_tokens": 2048
}
```

### Response Stream (SSE)
- **Token Chunks**: `data: {"token": "안녕하세요! ", "status": "streaming"}`
- **Completion Event**: `data: {"token": "", "status": "completed", "total_tokens": 482, "elapsed_seconds": 4.12}`

---

## 2. Chatbot A Synthesis Integration

### Function Signature
```python
def synthesize_beauty_solution(
    query: str,
    selected_reviews: list[dict],
    max_tokens: int = 2048,
    model_name: str = "qwen3.5-2b"
) -> str:
    """선별된 리뷰 팩트를 결합하여 2B 모델로 1,500자 완성형 뷰티 가이드 답변을 생성한다."""
```
