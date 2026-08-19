# Quickstart & Verification Guide: Redis Caching, Session & DBMS Optimization (Spec 019)

## 1. Prerequisites

- Docker & Docker Compose running.
- Python 3.12 virtualenv.
- `redis` package installed in subprojects (`pip install redis`).

---

## 2. Validation Scenarios

### Scenario 1: Redis Container Startup & Healthcheck
```bash
# 1. Start Redis container
docker compose up -d redis

# 2. Check Redis ping and memory limits
docker exec aiservice-redis redis-cli ping
docker exec aiservice-redis redis-cli config get maxmemory
```
*Expected Result*: `PONG`, `268435456` (256MB).

---

### Scenario 2: RAG Embedding & Rerank Cache Latency Benchmark
```python
import time, asyncio
from src.core.redis_manager import RedisManager

async def test_cache_speed():
    rm = RedisManager()
    text = "식물나라 토너 보습감과 피부 자극성"
    
    # 1st Call (Cache Miss -> Set Cache)
    t0 = time.perf_counter()
    vec = await rm.get_embedding("bge-m3", text)
    if not vec:
        await rm.set_embedding("bge-m3", text, [0.01] * 1024)
    t_miss = (time.perf_counter() - t0) * 1000
    
    # 2nd Call (Cache Hit)
    t1 = time.perf_counter()
    cached_vec = await rm.get_embedding("bge-m3", text)
    t_hit = (time.perf_counter() - t1) * 1000
    
    print(f"Cache Miss Latency: {t_miss:.2f}ms")
    print(f"Cache Hit Latency: {t_hit:.2f}ms (< 1ms target)")
    assert t_hit < 1.0

asyncio.run(test_cache_speed())
```

---

### Scenario 3: Streamlit & FastAPI Session History Persistence
1. 질의 1회 전송: "안녕하세요! 지성 피부에 좋은 토너 추천해주세요."
2. 브라우저 새로고침(F5) 또는 컨테이너 재시작.
3. 세션 ID로 대화 히스토리 요청 시 이전 질문과 어시스턴트 답변이 100% 복원되는지 확인.

---

### Scenario 4: MySQL Composite Index Performance Test
```sql
-- 캐시 미스 시 인덱스 스캔 실행 시간 검증 (목표: < 20ms)
EXPLAIN ANALYZE 
SELECT * FROM cosmetic_reviews 
WHERE product_id = 'P10023' 
ORDER BY review_date DESC 
LIMIT 20;
```
*Expected Result*: `Index Scan using idx_product_review_date`, Actual time < 10ms.
