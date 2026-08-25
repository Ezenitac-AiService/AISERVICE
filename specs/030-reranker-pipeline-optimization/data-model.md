# Data Model: Multi-Target RAG & Latency Optimization

**Feature**: `030-reranker-pipeline-optimization`  
**Date**: 2026-08-25  

## 1. Core State Entities

### `RagGraphState` (전역 그래프 상태)
```python
from typing import TypedDict, Optional, List, Dict, Any

class TargetEntity(TypedDict):
    target_id: str                   # e.g., "target_1"
    target_name: str                 # e.g., "차앤박 프로폴리스 에너지 앰플"
    brand_name: Optional[str]        # e.g., "차앤박"
    product_name: Optional[str]      # e.g., "프로폴리스 에너지 앰플"
    target_type: str                 # "PRODUCT" | "BRAND" | "ATTRIBUTE" | "SENTIMENT"
    attribute_query: Optional[str]   # e.g., "수분감", "장점", "주의점"
    spec_header: Optional[Dict[str, Any]] # {"price": 28000, "volume": "35ml", ...}

class CandidateReview(TypedDict):
    doc_id: str
    review_text: str
    target_id: str
    target_name: str
    first_stage_score: float
    rating: Optional[float]
    skin_type: Optional[str]

class RerankedReview(TypedDict):
    doc_id: str
    review_text: str
    target_id: str
    target_name: str
    rerank_score: float
    rank: int

class RagGraphState(TypedDict):
    trace_id: str
    session_id: str
    user_id: Optional[str]
    query: str
    normalized_query: str
    pattern_type: str                # "PATTERN_EXPLICIT_COMPARE" | "PATTERN_FEATURE_DISCOVERY" | ...
    target_entities: List[TargetEntity]
    search_pools: Dict[str, List[CandidateReview]] # {target_id: [10 candidate reviews]}
    reranked_contexts: Dict[str, List[RerankedReview]] # {target_id: [2~3 quota reviews]}
    context_text: str                # 6,000 token XML sandboxed context
    canary_token: str
    is_fallback: bool
    fallback_reason: Optional[str]
    target_errors: Dict[str, str]    # {target_id: "error message"}
    metrics: Dict[str, Any]
    error_log: List[str]
```

---

## 2. Redis Key Caching Schema

| 계층 | 키 패턴 (Key Pattern) | 데이터 타입 | TTL | 목적 |
| :--- | :--- | :---: | :---: | :--- |
| **L1** | `v1:rag:pool:{target_slug}:{attr_slug}` | String (JSON) | 12시간 | 1차 검색 풀 캐시 (MySQL + 내적 연산 제거) |
| **L2** | `emb:bge-m3:{sha256(norm_text)}` | String (JSON) | 7일 | BGE-M3 임베딩 벡터 캐시 |
| **L3** | `rerank:{sha256(query)}:{sha256(docs)}` | String (JSON) | 24시간 | BGE-Reranker 교차 점수 캐시 |
| **L4** | `checkpoint:{session_id}:{thread_id}` | Hash (Binary) | 3일 | LangGraph 멀티턴 세션 체크포인트 |
| **Lock** | `lock:rag:pool:{target_slug}` | String | 10초 | L1 캐시 스탬피드 방어 Single-flight Mutex |

---

## 3. Real-Time UI Event Model

### `SubStepEvent`
```python
class SubStepEvent(TypedDict):
    trace_id: str
    event_type: str                  # "step_update" | "token" | "complete" | "fallback_alert"
    step_id: str                     # "INTENT" | "SEARCH" | "RERANK" | "SYNTHESIS"
    step_name: str                   # "1. 의도 분석", "2. 타겟별 하이브리드 검색" 등
    sub_step: Optional[Dict[str, Any]] # {"target_index": 1, "total_targets": 2, "target_name": "차앤박 앰플", "action": "SEARCH_DONE", "count": 10}
    status: str                      # "pending" | "running" | "complete" | "fallback"
    fallback_info: Optional[Dict[str, Any]] # {"triggered": True, "label": "⚡ 신속 분석 모드"}
    elapsed_ms: float
    timestamp: float
```
