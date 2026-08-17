# API Contract: 올원챗 RAG 검색 응답 규약 (005-chatb-footer-cleanup)

**Feature**: `005-chatb-footer-cleanup`  
**Endpoint**: `POST /bteam/chatb/api/v1/search` (또는 로컬 컨테이너 `POST /api/v1/search`)

---

## 1. Request Payload

```json
{
  "query": "차앤박 프로폴리스 앰플 수분감을 분석해줘",
  "brand": null,
  "sentiment": null,
  "keyword": null,
  "top_n": 3
}
```

---

## 2. Response Payload (200 OK)

```json
{
  "llm_answer": "사용자님께서 문의하신 '차앤박 프로폴리스 앰플'의 수분감에 대한 실사용자 리뷰 분석 결과는 다음과 같습니다.\n\n실사용자들은 이 제품에 대해 '보습에는 차앤박 프로폴리스 앰플이 좋아요'라고 평가하며, 특히 수분감과 보습력을 긍정적으로 언급하고 있습니다. 따라서 피부 진정 및 수분 공급 측면에서 매우 추천할 만한 제품입니다.",
  "search_results": [
    {
      "rank": 1,
      "product_name": "프로폴리스 에너지 액티브 앰플 15ml",
      "brand_name": "차앤박",
      "category": "스킨케어",
      "review_score": 5,
      "separated_sentence": "보습에는 차앤박 프로폴리스 앰플이 좋아요",
      "display_name": "보습감",
      "sentiment_label": "긍정리뷰"
    }
  ],
  "model_used": "qwen3.5-4b"
}
```

> **품질 계약 규약**:
> 1. `llm_answer` 내부에는 어떠한 CJK 한자(漢字, `\u4e00-\u9fff`)나 `<think>` 태그가 포함되어서는 안 된다 (한자 비율: 0%).
> 2. `llm_answer`는 전문 뷰티 가이드의 친절하고 정중한 한국어 경어체로 작성된다.
