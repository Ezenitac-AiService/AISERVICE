# Data Model: 038-product-series-resolution-and-citation-enforcement

**Feature Branch**: `038-product-series-resolution-and-citation-enforcement`  
**Date**: 2026-08-26  

---

## 1. Core Data Entities & Schemas

### 1.1 `SeriesResolutionResult` (시리즈/라인명 매칭 결과)
```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class MatchedProductCandidate:
    product_id: str
    product_name: str
    brand_name: str
    category: str
    review_count: int
    average_rating: float
    product_url: str

@dataclass
class SeriesResolutionResult:
    is_series_query: bool
    detected_brand: Optional[str]
    series_keyword: Optional[str]
    candidates: List[MatchedProductCandidate]
    confidence: float
```

### 1.2 `NegativeAspectDefinition` (뷰티 부정 속성 정의)
```python
from dataclasses import dataclass
from enum import Enum

class AspectPolarity(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"

@dataclass
class NegativeAspectDefinition:
    term: str
    canonical_meaning: str
    polarity: AspectPolarity
    target_section: str  # e.g., "⚠️ 아쉬운 점 / 주의할 점"
```

### 1.3 `ChatStreamRequest` & `ChatStreamEvent` (FastAPI SSE 통신 스키마)
```python
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class ChatStreamRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    category_hint: Optional[str] = None
    bypass_cache: bool = False

class ChatStreamEvent(BaseModel):
    event_type: str  # "step_update" | "token" | "queue_waiting" | "fallback_alert" | "complete" | "error"
    step_id: Optional[str] = None
    step_name: Optional[str] = None
    status: Optional[str] = None
    token: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    reference_reviews: Optional[List[Dict[str, Any]]] = None
    error_message: Optional[str] = None
```
