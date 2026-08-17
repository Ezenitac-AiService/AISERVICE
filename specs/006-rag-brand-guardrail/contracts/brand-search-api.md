# API Contract: 올리뷰 프론트엔드 브랜드 조회 API (006-rag-brand-guardrail)

**Feature**: `006-rag-brand-guardrail`  
**Endpoint**: `GET /bteam/oliview/api/search-brands` (또는 `GET /bteam/oliview/api/brands`)

---

## 1. Request Parameters

```text
GET /bteam/oliview/api/search-brands?keyword=헤라
```

---

## 2. Response Payload (200 OK)

```json
{
  "success": true,
  "brands": [
    {
      "brand_id": 68,
      "brand_name": "헤라",
      "brand_code": "A002992"
    }
  ]
}
```
