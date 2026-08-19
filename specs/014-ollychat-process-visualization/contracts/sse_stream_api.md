# API Contract: `/api/v1/search/stream` (Server-Sent Events)

**Feature**: `014-ollychat-process-visualization`  
**Endpoint**: `POST /api/v1/search/stream`  
**Content-Type**: `text/event-stream`  
**Target**: 올리챗 B (`project_ragapi.py` ➡️ `index.html`)  

---

## 1. 개요

올리챗 B 웹 UI와의 실시간 4단계 RAG 진행 상태, 토큰 타이핑 스트리밍, 완료 메타데이터 전송을 위한 SSE(Server-Sent Events) 프로토콜 규격입니다.

---

## 2. 요청 (Request)

### Headers
```http
POST /api/v1/search/stream HTTP/1.1
Host: localhost:8000
Content-Type: application/json
Accept: text/event-stream
```

### Request Body (JSON)
```json
{
  "query": "컬러그램 탕후루 탱글 꿀로스의 발림성 장단점을 분석해줘",
  "brand": "컬러그램",
  "sentiment": null,
  "keyword": null,
  "fetch_k": 20,
  "top_n": 5,
  "model": "qwen3.5-4b"
}
```

---

## 3. SSE 이벤트 스트림 규격 (Event Stream Specification)

서버는 처리 단계에 따라 아래 순서로 이벤트를 클라이언트에 스트리밍합니다.

### Event 1: `step` (진행 단계 전환 이벤트)
```http
event: step
data: {"phase": "INTENT_ANALYSIS", "label": "🔍 질문 의도 및 화장품 속성 분석 중...", "status": "running", "elapsed_sec": 0.05, "progress_percent": 25}

event: step
data: {"phase": "HYBRID_SEARCH", "label": "📚 리뷰 하이브리드 검색 중 (BM25 + BGE-M3)...", "status": "running", "elapsed_sec": 0.32, "progress_percent": 50}

event: step
data: {"phase": "RERANKING", "label": "⚖️ BGE-Reranker 순위 재정렬 중...", "status": "running", "elapsed_sec": 0.75, "progress_percent": 75}

event: step
data: {"phase": "LLM_SYNTHESIS", "label": "🧠 LLM 심층 분석 및 맞춤 답변 생성 중...", "status": "running", "elapsed_sec": 1.10, "progress_percent": 90}
```

### Event 2: `token` (LLM 답변 실시간 토큰 스트리밍)
```http
event: token
data: {"token": "컬러"}

event: token
data: {"token": "그램 "}

event: token
data: {"token": "탕후루 "}
```

### Event 3: `complete` (최종 완료 및 메타데이터 이벤트)
```http
event: complete
data: {
  "phase": "COMPLETED",
  "label": "✅ 리뷰 종합 분석 완료",
  "total_latency_sec": 1.84,
  "searched_review_count": 20,
  "selected_review_count": 5,
  "model_used": "qwen3.5-4b",
  "fallback_triggered": false,
  "reference_reviews": [
    {
      "rank": 1,
      "product_name": "탕후루 탱글 꿀로스",
      "brand_name": "컬러그램",
      "category": "립메이크업",
      "review_score": 5,
      "attribute_tag": "발림성",
      "sentiment_label": "긍정",
      "separated_sentence": "끈적임 없이 부드럽고 촉촉하게 펴 발립니다.",
      "rerank_score": 0.912
    }
  ]
}
```

### Event 4: `error` (예외 및 0건 검색 장애 이벤트)
```http
event: error
data: {
  "phase": "ERROR",
  "label": "⚠️ 분석 실패",
  "error_message": "조건에 일치하는 등록 리뷰가 존재하지 않습니다.",
  "retry_query": "컬러그램 탕후루 탱글 꿀로스",
  "suggested_chips": ["컬러그램 꿀로스", "립메이크업 발림성", "식물나라 선크림"]
}
```

---

## 4. HTTP 상태 코드

- `200 OK`: SSE 스트림 정상 연결 및 데이터 전송 시작.
- `422 Unprocessable Entity`: 필수 입력 파라미터(`query`) 누락 또는 스키마 불일치.
- `500 Internal Server Error`: 치명적 서버 오류 (스트림 시작 전 실패 시 일반 JSON 응답).
