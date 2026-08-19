# Data Model & Schema: Redis Caching, Session & DBMS Optimization (Spec 019)

## 1. Redis Key Schema & Data Structures

| 네임스페이스 | 키 포맷 (Key Pattern) | 데이터 타입 | TTL | 목적 및 설명 |
| :--- | :--- | :---: | :---: | :--- |
| **Embedding Cache** | `emb:{model_id}:{sha256(text)}` | `String` (JSON Vector) | 7일 (604800s) | BGE-M3 1024차원 실수 벡터 리스트 |
| **Rerank Cache** | `rerank:{query_hash}:{doc_ids_hash}` | `String` (JSON Scores) | 24시간 (86400s) | BGE-Reranker Top-K 유사도 점수 맵 |
| **LLM Response Cache** | `llm:cache:{model_id}:{prompt_hash}` | `String` (JSON Response) | 1시간 (3600s) | 자주 묻는 FAQ 및 고정 질의 LLM 완성 텍스트 |
| **Chat Session History** | `session:{session_id}:history` | `List` (JSON Messages) | 3일 (259200s, Sliding) | 멀티턴 대화 히스토리 (`[{"role": "...", "content": "..."}]`) |
| **Async Job Queue** | `queue:pilos:jobs` | `List` (JSON Job Payload) | 무제한 (BRPOP 소비) | PILOS 감정 분석 작업 대기열 (`LPUSH`/`BRPOP`) |
| **Distributed Lock** | `lock:pilos:{review_id}` | `String` (Worker Token) | 30초 (30000ms) | 리뷰 중복 분석 방지 분산 락 (`SETNX`) |
| **Rate Limiter** | `ratelimit:{client_ip}` | `String` / `ZSet` | 60초 (Window) | 클라이언트별 초당/분당 호출 제한 토큰 버킷 |

---

## 2. Pydantic Entities for Caching & Sessions

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class CachedEmbedding(BaseModel):
    model_id: str
    text_hash: str
    dimension: int = 1024
    vector: List[float]
    created_at: int

class CachedRerankScore(BaseModel):
    query_hash: str
    doc_ids_hash: str
    results: List[Dict[str, Any]]
    created_at: int

class ChatMessageItem(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant)$")
    content: str
    timestamp: Optional[int] = None

class SessionHistory(BaseModel):
    session_id: str
    messages: List[ChatMessageItem] = Field(default_factory=list)
    last_active: int
    ttl_seconds: int = 259200

class PilosJobPayload(BaseModel):
    job_id: str
    review_id: str
    product_id: str
    review_text: str
    status: str = "pending"
    enqueued_at: int
```

---

## 3. MySQL Database Index Models (`bteam_db` & `pilos-db`)

### `bteam_db.cosmetic_reviews` 복합 인덱스
```sql
-- 1. 상품별 최신 리뷰 고속 조회 복합 인덱스
CREATE INDEX idx_product_review_date ON cosmetic_reviews (product_id, review_date DESC);

-- 2. 브랜드 및 평점별 필터링 복합 인덱스
CREATE INDEX idx_brand_rating ON cosmetic_reviews (brand_id, rating);
```

### `pilos-db.review_sentiment_results` 복합 인덱스
```sql
-- 3. 감정 분석 완료 상태 및 일자별 집계 인덱스
CREATE INDEX idx_sentiment_status_date ON review_sentiment_results (status, analyzed_at DESC);
```
