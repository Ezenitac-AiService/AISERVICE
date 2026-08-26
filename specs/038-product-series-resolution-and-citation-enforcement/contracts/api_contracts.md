# API & UI Interface Contracts: 038-product-series-resolution-and-citation-enforcement

---

## 1. FastAPI SSE Streaming Endpoint Contract

### `POST /api/v1/chat/stream`
- **Description**: 실시간 RAG 토큰 및 상태 이벤트를 Server-Sent Events(SSE)로 스트리밍.
- **Request Body**:
  ```json
  {
    "query": "헤라 센슈얼 립 촉촉함과 각질부각 분석해줘",
    "session_id": "sess_20260826_01",
    "category_hint": "메이크업",
    "bypass_cache": false
  }
  ```
- **SSE Stream Protocol**:
  ```text
  event: step_update
  data: {"step_id": "INTENT", "step_name": "🔍 1. 의도 분석", "status": "running"}

  event: step_update
  data: {"step_id": "SEARCH", "step_name": "📚 2. 시리즈 상품 2종 발굴", "status": "complete"}

  event: token
  data: {"token": "헤라 "}

  event: token
  data: {"token": "센슈얼 "}

  event: complete
  data: {"total_latency_sec": 1.45, "selected_review_count": 4, "reference_reviews": [...]}
  ```

---

## 2. Responsive UI Breakpoints Contract

| Breakpoint | Target Device | Layout Specification |
|:---|:---|:---|
| **$\ge 768\text{px}$** | Desktop / Laptop | 상단 2열 그리드 `[1.6 : 1.4]` (브랜드/카테고리/속성 칩 + 1클릭 질문 예시), 너비 1200px 중앙 정렬, 하단 블러 바 |
| **$< 768\text{px}$** | Mobile / Tablet | 상단 가로 스크롤 칩 바, Thumb-Zone 하단 고정 바, `[리뷰 N]` 터치 시 슬라이드업되는 **바텀 시트 드로어(Bottom Sheet)** |
