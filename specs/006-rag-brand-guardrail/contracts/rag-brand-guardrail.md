# API Contract: RAG 부재 브랜드 질의 응답 규약 (006-rag-brand-guardrail)

**Feature**: `006-rag-brand-guardrail`  
**Endpoint**: `POST /bteam/chatb/api/v1/search` (또는 로컬 컨테이너 `POST /api/v1/search`)

---

## 1. Request Payload (미등록/부재 브랜드 질의)

```json
{
  "query": "헤라 스킨케어 제품 추천해줘",
  "brand": null,
  "top_n": 3
}
```

---

## 2. Response Payload (200 OK - 부재 브랜드 표준 0-결과 폴백)

```json
{
  "llm_answer": "죄송합니다. 현재 '헤라' 브랜드의 등록 상품 및 리뷰 데이터가 올리뷰에 존재하지 않습니다. 올리브영에 등록된 다른 브랜드명으로 검색해 주세요.",
  "search_results": [],
  "model_used": "brand-guardrail"
}
```

> **품질 계약 규약**:
> 1. `search_results`는 빈 배열(`[]`)로 반환되어야 한다.
> 2. `llm_answer`에 `[익명]`이나 타사 제품 추천 문장이 일체 포함되지 않아야 한다.
