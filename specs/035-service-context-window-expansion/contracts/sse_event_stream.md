# Contract: Living Agent Inspector SSE Event Stream

**Endpoint**: `POST /bteam/chatb/api/v1/search/stream` & `POST /api/v1/search/stream`  
**Content-Type**: `text/event-stream`

---

## 1. Event Sequence Specification

LangGraph `Compiled StateGraph` 실행 시 다음과 같은 SSE 이벤트 스트림이 순차/동적 방출됩니다:

### 1.1 Node Start / Update Event (`event: step_update`)
```text
event: step_update
data: {
  "trace_id": "tr_1787649200",
  "event_type": "step_update",
  "node_id": "INTENT_ANALYSIS",
  "parent_node_id": null,
  "title": "1. 의도 및 과거 대화 지시어 분석",
  "status": "running",
  "is_branch": false,
  "elapsed_ms": 120,
  "badge_text": "다중 비교 의도 식별 (차앤박 vs 닥터지)",
  "timestamp": 1787649200.12
}
```

---

### 1.2 Branch Fork Event (`event: step_update` with `is_branch: true`)
1차 검색 품질 미달 또는 세션 역조회 시 동적 자식 노드가 방출됩니다:
```text
event: step_update
data: {
  "trace_id": "tr_1787649200",
  "event_type": "step_update",
  "node_id": "QUERY_REFORMULATION",
  "parent_node_id": "QUALITY_GRADE",
  "title": "↳ 🔄 하이브리드 재검색 (사전 동의어 + Fast LLM 문맥 쿼리)",
  "status": "running",
  "is_branch": true,
  "elapsed_ms": 480,
  "badge_text": "2차 보량 검색 중 (추가 15건 수집)",
  "timestamp": 1787649200.60
}
```

---

### 1.3 Deep Recall Event (`event: step_update` with `is_branch: true`)
```text
event: step_update
data: {
  "trace_id": "tr_1787649200",
  "event_type": "step_update",
  "node_id": "DEEP_RECALL",
  "parent_node_id": "INTENT_ANALYSIS",
  "title": "↳ 🧠 과거 대화 심층 회상 (Turn 7 '진정 수분 크림' 원본 복원)",
  "status": "complete",
  "is_branch": true,
  "elapsed_ms": 25,
  "badge_text": "Redis L4 세션 원본 복원 완료",
  "timestamp": 1787649200.65
}
```

---

### 1.4 Token Streaming Event (`event: token`)
```text
event: token
data: {
  "trace_id": "tr_1787649200",
  "event_type": "token",
  "token": "## [제품 비교 분석 결과]\n\n",
  "timestamp": 1787649201.20
}
```

---

### 1.5 Pipeline Complete Event (`event: complete`)
```text
event: complete
data: {
  "trace_id": "tr_1787649200",
  "event_type": "complete",
  "total_latency_sec": 3.82,
  "is_cached": false,
  "context_tier": "16K_BASELINE",
  "selected_review_count": 12,
  "recalled_turn": 7,
  "executed_nodes": ["INTENT_ANALYSIS", "SEARCH_PER_TARGET", "QUALITY_GRADE", "QUERY_REFORMULATION", "DEEP_RECALL", "CONTEXT_BUILDER", "SYNTHESIS_STREAM"],
  "reference_reviews": [
    {
      "rank": 1,
      "product_name": "닥터지 레드 블레미쉬 크림",
      "brand_name": "닥터지",
      "clean_text": "진정 효과가 뛰어나고 끈적이지 않아서 3통째 사용 중입니다.",
      "rerank_score": 0.892,
      "product_url": "https://www.oliveyoung.co.kr/..."
    }
  ],
  "timestamp": 1787649204.02
}
```
