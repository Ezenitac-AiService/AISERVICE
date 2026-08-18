# Interface Contract: Oliview Product Detail & Analysis API

**Service**: `bteam_backend (oliview_backend:5050)`
**Ingress Path**: `/bteam/oliview/api/`

---

## 1. 상품 상세 정보 조회 (`GET /bteam/oliview/api/products/{product_id}`)

### Description
특정 상품의 기본 메타데이터(이름, 브랜드, 이미지) 및 옵션 목록을 반환합니다.

### Path Parameters
- `product_id` (integer, required): 상품 고유 식별자

### Response 200 OK
```json
{
  "success": true,
  "product": {
    "product_id": 7,
    "brand_id": 1,
    "brand_name": "헤라",
    "product_name": "블랙 쿠션 SPF34 PA++",
    "product_image_url": "https://image.oliveyoung.co.kr/...",
    "created_at": "2026-01-01 00:00:00"
  },
  "options": [
    {
      "product_option_id": 12,
      "product_id": 7,
      "option_name": "21N1 바닐라"
    }
  ],
  "reviews": []
}
```

### Response 404 Not Found
```json
{
  "success": false,
  "message": "상품을 찾을 수 없습니다."
}
```

---

## 2. 감성 분석 리포트 조회 (`GET /bteam/oliview/api/products/{product_id}/analysis-report`)

### Description
속성별 긍정/부정 통계, 레이더 차트 데이터, AI 요약 텍스트 및 분석 문장 목록을 반환합니다.

### Query Parameters
- `tab` (string, optional): `'maintain'` (유지할 점), `'improve'` (개선점), `'neutral'` (중립). 기본값: `'maintain'`
- `attribute_name` (string, optional): 특정 속성 필터링 (예: `'밀착력'`)
- `sentiment` (string, optional): `'positive'`, `'negative'`, `'neutral'`, `'all'`

### Response 200 OK
```json
{
  "success": true,
  "radar_data": [
    {
      "attribute_id": 1,
      "attribute_name": "밀착력",
      "total_count": 150,
      "pos_count": 135,
      "neg_count": 10,
      "neu_count": 5,
      "score": 0.90,
      "positive_summary": "피부에 얇고 균일하게 밀착되어 묻어남이 적다는 호평이 다수입니다.",
      "negative_summary": "건성 피부의 경우 기초가 부족하면 건조하게 밀착된다는 의견이 있습니다."
    }
  ],
  "overall_stats": {
    "total_sentence_count": 1200,
    "positive_count": 980,
    "negative_count": 150,
    "neutral_count": 70,
    "positive_ratio": 81.67,
    "negative_ratio": 12.50
  },
  "overall_report": {
    "keep_summary": "우수한 밀착력과 커버력, 고급스러운 패키지 디자인이 핵심 강점입니다.",
    "improvement_summary": "건성 피부를 위한 보습감 보완 및 다양한 호수 확장이 요구됩니다.",
    "overall_summary": "프리미엄 쿠션 시장에서 독보적인 유지력과 커버력을 제공하는 스테디셀러입니다."
  },
  "reviews_data": [
    {
      "review_id": 1024,
      "sequence_no": 1,
      "sentiment_sentence": "바르자마자 피부에 싹 밀착돼서 너무 좋아요.",
      "sentiment_label": "positive",
      "rating": 5,
      "review_created_at": "2026-08-10",
      "option_name": "21N1 바닐라",
      "full_review_text": "바르자마자 피부에 싹 밀착돼서 너무 좋아요. 마스크에도 거의 안 묻어납니다.",
      "attribute_name": "밀착력"
    }
  ]
}
```

---

## 3. 리뷰 상세 목록 조회 (`GET /bteam/oliview/api/products/{product_id}/reviews-detail`)

### Query Parameters
- `sort` (string, optional): `'all'`, `'high'`, `'low'`
- `attribute_name` (string, optional): 특정 속성 필터링

### Response 200 OK
```json
{
  "success": true,
  "reviews": [
    {
      "review_id": 1024,
      "rating": 5,
      "review_date": "2026-08-10",
      "review_content": "바르자마자 피부에 싹 밀착돼서 너무 좋아요. 마스크에도 거의 안 묻어납니다.",
      "option_name": "21N1 바닐라",
      "sentences": [
        {
          "aspect_sentence_id": 2048,
          "sequence_no": 1,
          "separated_sentence": "바르자마자 피부에 싹 밀착돼서 너무 좋아요.",
          "sentiment_label": "positive",
          "attribute_name": "밀착력"
        }
      ],
      "counts": {
        "positive": 1,
        "negative": 0,
        "neutral": 0
      }
    }
  ]
}
```
