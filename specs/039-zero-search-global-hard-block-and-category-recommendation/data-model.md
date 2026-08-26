# Data Model & Schema Specification: Feature 039

**Feature**: `039-zero-search-global-hard-block-and-category-recommendation`  
**Created**: 2026-08-26  
**Status**: Completed  

---

## 1. Core Data Structures & Models

### 1.1 In-Memory Dynamic Catalog Models (`oliview_core/tools/dynamic_catalog_index.py`)

```python
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional
from enum import Enum


class AppRunMode(str, Enum):
    DEMO = "DEMO"
    PRODUCTION = "PRODUCTION"


@dataclass
class ProductCatalogEntry:
    product_id: int
    product_name: str
    clean_product_name: str
    brand_name: str
    category: str
    total_review_count: int
    avg_rating: float
    series_name: Optional[str] = None
    product_url: Optional[str] = None


@dataclass
class DynamicCatalogIndexState:
    active_brands: Set[str] = field(default_factory=set)
    products_by_category: Dict[str, List[ProductCatalogEntry]] = field(default_factory=dict)
    product_by_name: Dict[str, ProductCatalogEntry] = field(default_factory=dict)
    product_by_id: Dict[int, ProductCatalogEntry] = field(default_factory=dict)
    is_loaded: bool = False
    last_loaded_timestamp: float = 0.0
```

---

### 1.2 Aspect Summary & Recommendation Target Models

```python
@dataclass
class AspectSentimentAggregate:
    summary_id: int
    product_id: int
    aspect_name: str  # e.g., '수분감', '각질부각', '밀착력', '지속력'
    positive_count: int
    negative_count: int
    neutral_count: int
    positive_ratio: float  # positive_count / (positive_count + negative_count + 1e-6)
    composite_score: float  # positive_ratio * 0.7 + log(total_count + 1) * 0.3
    top_sentence_ids: List[int] = field(default_factory=list)


@dataclass
class CategoryRecommendationCandidate:
    product_id: int
    product_name: str
    brand_name: str
    category: str
    target_aspect: str
    positive_ratio: float
    total_review_count: int
    avg_rating: float
    rank: int
```

---

### 1.3 Groundedness & Zero-Search Guard State

```python
@dataclass
class ZeroSearchVerdict:
    is_zero_search: bool
    reason: str  # 'OUT_OF_CATALOG_BRAND', 'ZERO_REVIEWS_IN_DB', 'RERANK_FILTER_EMPTY'
    suggested_chips: List[str] = field(default_factory=list)
    template_text: str = ""
    latency_ms: float = 0.0


@dataclass
class GroundednessSanitizerResult:
    cleaned_markdown: str
    removed_fictional_quotes: List[str]
    valid_citation_count: int
    has_violations: bool
```

---

## 2. Relational Database Schema (MySQL)

```sql
-- 1. 리뷰 보유 실존 상품 뷰 (v_active_rag_catalog)
CREATE OR REPLACE VIEW v_active_rag_catalog AS
SELECT 
    p.product_id,
    p.product_name,
    p.brand_name,
    p.category,
    COUNT(r.review_id) AS total_review_count,
    COALESCE(AVG(r.rating), 5.0) AS avg_rating,
    p.product_url
FROM products p
INNER JOIN reviews r ON p.product_id = r.product_id
GROUP BY p.product_id, p.product_name, p.brand_name, p.category
HAVING total_review_count >= 1;

-- 2. 상품별 속성 감성 집계 뷰 / 테이블 (product_aspect_summaries)
CREATE TABLE IF NOT EXISTS product_aspect_summaries (
    summary_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    product_id BIGINT NOT NULL,
    aspect_name VARCHAR(50) NOT NULL,
    positive_count INT NOT NULL DEFAULT 0,
    negative_count INT NOT NULL DEFAULT 0,
    neutral_count INT NOT NULL DEFAULT 0,
    positive_ratio FLOAT NOT NULL DEFAULT 0.0,
    composite_score FLOAT NOT NULL DEFAULT 0.0,
    top_sentence_ids JSON NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_aspect_prod (aspect_name, composite_score DESC),
    INDEX idx_product_id (product_id)
);
```

---

## 3. LangGraph State Extension (`RagGraphState`)

```python
class RagGraphState(TypedDict, total=False):
    # Existing fields
    trace_id: str
    query: str
    tenant_id: str
    session_id: str
    target_entities: List[TargetEntity]
    reranked_contexts: Dict[str, List[RerankedReview]]
    
    # Feature 039 Extensions
    app_run_mode: str                      # "DEMO" or "PRODUCTION"
    is_zero_review_state: bool             # True when total selected reviews == 0
    zero_search_verdict: ZeroSearchVerdict # Zero search explanation & chips
    groundedness_violations: List[str]     # Stripped fictional user phrases
    category_candidates: List[CategoryRecommendationCandidate]
```
