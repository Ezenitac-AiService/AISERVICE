# Data Model: 브랜드 엔티티 및 품질 검증 데이터 모델 (006-rag-brand-guardrail)

**Feature**: `006-rag-brand-guardrail`  
**Spec**: [spec.md](file:///c:/AISERVICE/specs/006-rag-brand-guardrail/spec.md) | **Plan**: [plan.md](file:///c:/AISERVICE/specs/006-rag-brand-guardrail/plan.md)

---

## 1. 불용어 및 브랜드 엔티티 매핑 스키마

```python
# 일반 검색 오염을 유발하는 불용어 세트
RAG_STOPWORDS = {
    "스킨케어", "화장품", "제품", "추천", "추천해줘", "추천해",
    "알려줘", "분석해줘", "분석해", "비교해줘", "좋은", "어떤게",
    "인기", "순위", "리뷰", "사용기", "모음", "베스트"
}

class BrandEntity(BaseModel):
    brand_id: int
    brand_name: str
    brand_code: str
    has_reviews: bool = False
```

---

## 2. RAG 검색 품질 응답 모델 (Pydantic v2 Schema)

```python
class RecommendedProduct(BaseModel):
    rank: int
    product_name: str          # NULL/빈값/'미분류 상품' 절대 불가
    brand_name: str            # NULL/빈값/'[익명]'/'미분류 브랜드' 절대 불가
    category: str
    review_score: int
    separated_sentence: str
    display_name: str
    sentiment_label: str

class RagSearchResponse(BaseModel):
    llm_answer: str            # 한자 0%, [익명] 0%의 자연스러운 순수 한국어 솔루션 또는 부재 브랜드 표준 안내문
    search_results: List[RecommendedProduct]
    model_used: Optional[str] = None
```
