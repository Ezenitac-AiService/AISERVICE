# Data Model: 통합 3대 챗봇 맞춤형 UX 고도화

**Feature**: `015-unified-chatbots-tailored-ux`  
**Date**: 2026-08-19

---

## 1. 3대 챗봇 파이프라인 단계 정의 (PipelinePhase)

### 1.1 올리챗 A & 올원챗 B (Beauty Domain)
```python
from enum import Enum

class BeautyPipelinePhase(str, Enum):
    INTENT_ANALYSIS = "INTENT_ANALYSIS"      # 1단계: 질문 의도 및 화장품 속성 분석
    HYBRID_SEARCH = "HYBRID_SEARCH"          # 2단계: BGE-M3 + SQL/ChromaDB 하이브리드 검색
    RERANKING = "RERANKING"                  # 3단계: BGE-Reranker 순위 재정렬
    LLM_SYNTHESIS = "LLM_SYNTHESIS"          # 4단계: 맞춤 답변 실시간 생성
    COMPLETED = "COMPLETED"                  # 5단계: 최종 완료 및 참조 리뷰 렌더링
    ERROR = "ERROR"                          # 6단계: 0건 검색 또는 통신 오류
```

### 1.2 A-Team PILOS 챗봇 (Finance Domain)
```python
class FinancePipelinePhase(str, Enum):
    IDENTIFY_STOCK = "IDENTIFY_STOCK"                        # 1단계: 종목 식별 및 질의 의도 파악
    SUPPLY_DEMAND_METRIC = "SUPPLY_DEMAND_METRIC"            # 2단계: 확정 수급지수 및 종목 랭킹 집계
    NEWS_SENTIMENT_VERIFICATION = "NEWS_SENTIMENT_VERIFICATION"  # 3단계: 실시간 뉴스/공시 감성 지수 교차 검증
    LLM_REPORT_SYNTHESIS = "LLM_REPORT_SYNTHESIS"            # 4단계: LLM 종합 리포트 생성
    COMPLETED = "COMPLETED"                                  # 5단계: 최종 완료 및 참조 뉴스/공시 렌더링
    ERROR = "ERROR"                                          # 6단계: 예외 및 복구 상태
```

---

## 2. 참조 원문 및 이커머스/금융 연동 DTO

### 2.1 뷰티 도메인 참조 리뷰 (ReferenceReview)
```python
from pydantic import BaseModel, Field

class ReferenceReview(BaseModel):
    rank: int = Field(default=1, description="리랭킹 순위")
    product_name: str = Field(default="", description="상품명")
    clean_product_name: str = Field(default="", description="노이즈 제거된 검색용 핵심 상품명")
    brand_name: str = Field(default="", description="브랜드명")
    category: str = Field(default="", description="화장품 카테고리")
    attribute_tag: str = Field(default="", description="속성 태그 (발림성, 수분감 등)")
    sentiment_label: str = Field(default="", description="감성 라벨 (긍정, 부정)")
    separated_sentence: str = Field(default="", description="실제 리뷰 문장 원문")
    oliveyoung_search_url: str = Field(default="", description="올리브영 공식몰 정밀 검색 URL")
```

### 2.2 금융 도메인 참조 뉴스/공시 (ReferenceFinancialSource)
```python
class ReferenceFinancialSource(BaseModel):
    rank: int = Field(default=1, description="근거 순위")
    stock_code: str = Field(default="", description="종목 코드 (예: 005930)")
    stock_name: str = Field(default="", description="종목명 (예: 삼성전자)")
    source_title: str = Field(default="", description="뉴스 기사 제목 또는 공시 제목")
    publisher: str = Field(default="", description="언론사 또는 공시 기관 (DART)")
    sentiment_score: float = Field(default=0.0, description="감성 점수 (-1.0 ~ +1.0)")
    published_date: str = Field(default="", description="발행 일자")
    external_url: str = Field(default="", description="네이버 증권 또는 DART 공시 바로가기 URL")
```

---

## 3. 세션 상태 및 큐 모델 (Streamlit Session State)

```python
class StreamlitChatSessionState:
    messages: list[dict]                     # 대화 히스토리 리스트
    selected_category: str                   # 선택된 화장품 카테고리
    selected_attribute: str                  # 선택된 화장품 속성
    pending_query: str | None = None         # 1클릭 즉시 실행용 단일 큐
    last_completed_metadata: dict | None = None # 직전 완료 메타데이터
```
