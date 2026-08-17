# Data Model: 올원챗 프롬프트 및 한자 정제 텍스트 가드레일 모델 (005-chatb-footer-cleanup)

**Feature**: `005-chatb-footer-cleanup`  
**Spec**: [spec.md](file:///c:/AISERVICE/specs/005-chatb-footer-cleanup/spec.md) | **Plan**: [plan.md](file:///c:/AISERVICE/specs/005-chatb-footer-cleanup/plan.md)

---

## 1. 한자어 치환 매핑 테이블 (Hanja-to-Hangul Mapping Dictionary)

```python
HANJA_TO_HANGUL_MAP = {
    # 핵심 분석/추천 용어
    "結果": "결과", "推薦": "추천", "效果": "효과", "成分": "성분",
    "皮膚": "피부", "使用": "사용", "分析": "분석", "製品": "제품",
    "價格": "가격", "滿足": "만족", "總評": "총평", "結論": "결론",
    "優點": "장점", "缺點": "단점", "特徵": "특징", "評價": "평가",
    "容量": "용량", "適合": "적합", "機能": "기능", "改善": "개선",

    # 화장품 속성 및 제형 용어
    "保濕": "보습", "水分": "수분", "彈力": "탄력", "敏感": "민감",
    "塗抹": "발림", "油分": "유분", "吸水": "흡수", "鎭靜": "진정",
    "鎮靜": "진정", "乾燥": "건조", "滋潤": "촉촉함", "補水": "수분 공급",
    "溫和": "순함", "角質": "각질", "美白": "미백", "皺紋": "주름",
    "潔面": "클렌징", "精華": "에센스", "乳液": "로션", "面霜": "크림",
    "防曬": "선케어", "遮瑕": "커버", "持久": "지속력", "香氣": "향",
    "刺痛": "따가움", "清爽": "산뜻함", "黏膩": "끈적임"
}
```

---

## 2. RAG 응답 모델 데이터 구조 (Pydantic v2 Schema)

```python
class RecommendedProduct(BaseModel):
    rank: int
    product_name: str
    brand_name: str
    category: str
    review_score: int
    separated_sentence: str
    display_name: str
    sentiment_label: str

class RagSearchResponse(BaseModel):
    llm_answer: str          # 한자 0% 및 CoT 태그가 완전히 정제된 순수 한국어 답변
    search_results: List[RecommendedProduct]
    model_used: Optional[str] = None
```
