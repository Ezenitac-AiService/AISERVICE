# Research & Technical Decisions: Redis Caching, Session & DBMS Optimization (Spec 019)

## 1. Multi-Layered RAG Caching Architecture (2026 Standard)

### Decision
`model_gateway` 및 `bteam/oliview_core`에 3단계 계층 캐시를 구성한다:
1. **Layer 1: Exact Match (KV Cache)**: SHA256 해시 키 기반 즉시 반환 (< 0.2ms).
2. **Layer 2: Embedding Vector Cache**: BGE-M3 임베딩 벡터(`emb:{model}:{sha256}`) 캐싱 (< 0.5ms).
3. **Layer 3: Reranker Score Cache**: `rerank:{query_hash}:{doc_ids_hash}` (Top-K 점수 캐싱, TTL 24시간).

### Rationale
- 임베딩 및 리랭킹 연산은 동일한 텍스트에 대해 수학적으로 일정한 결정론적(Deterministic) 결과값을 가짐.
- 캐시 히트 시 모델 게이트웨이의 GPU/CPU 연산 비용을 100% 절감하고 RAG 지연 시간을 100ms → 0.5ms 이하로 단축.

### Alternatives Considered
- *In-Memory Python Dict Cache*: 멀티 프로세스 및 컨테이너 간 공유 불가, 재시작 시 휘발됨.
- *Disk-based SQLite Cache*: I/O 동시성 경합 및 파일 락 문제 발생.

---

## 2. Distributed Session Store & Multi-Turn Chat Persistence

### Decision
`ChatA`(Streamlit), `ChatB`(FastAPI), `pilos_web`의 세션 대화 히스토리를 Redis `session:{session_id}:history` (`List` of JSON)로 관리하며 슬라이딩 윈도우 TTL(3일)을 적용한다.

### Rationale
- Streamlit 및 FastAPI 컨테이너 재시작이나 사용자의 웹 브라우저 새로고침 시에도 대화 맥락(Context)이 100% 보존됨.
- 대화 히스토리의 최대 토큰/메시지 수(최근 20개 메시지)를 `LTRIM`으로 자동 슬라이딩하여 메모리 효율 극대화.

---

## 3. PILOS Asynchronous Job Queue & Distributed Locking

### Decision
- **Job Queue**: `queue:pilos:jobs` (Redis `LPUSH` / `BRPOP` 패턴)
- **Distributed Lock**: `lock:pilos:{review_id}` (Redis `SET key val NX PX 30000` Redlock 패턴)

### Rationale
- MySQL 지속 폴링 방식 대비 DB CPU 및 커넥션 부하가 95% 감소.
- 분산 워커 환경에서 동일한 화장품 리뷰나 배치 분석 작업의 중복 실행을 완벽히 방어.

---

## 4. Token Bucket Rate Limiter (Protection Layer)

### Decision
Redis Lua Script 기반 원자적 토큰 버킷 속도 제한기(`ratelimit:client:{ip_or_token}`) 구축.

### Rationale
- GPU VRAM(GTX 1070 8GB)의 초당 추론 용량을 초과하는 비정상적인 버스트 트래픽을 API 게이트웨이 레벨에서 `429 Too Many Requests`로 즉시 차단하여 LLM 서버 과부하 방지.

---

## 5. DBMS (MySQL & ChromaDB) Co-Optimization

### Decision
- **MySQL Indexing**: `bteam_db` 및 `pilos-db`의 주요 검색 테이블에 `(product_id, review_date)`, `(brand_id, rating)` 복합 인덱스 생성.
- **SQLAlchemy Pool**: `pool_size=10, max_overflow=20, pool_recycle=1800, pool_pre_ping=True` 튜닝.
- **ChromaDB HNSW**: `hnsw:search_ef = 64` 설정으로 1차 벡터 검색 속도 30% 향상.

### Rationale
- Redis 캐시 미스(Cache Miss) 발생 시에도 원본 RDBMS 쿼리 시간이 500ms → 20ms 이하로 유지되어 백엔드 안정성 보장.

---

## 6. Circuit Breaker & Graceful Degradation Strategy

### Decision
모든 Redis 클라이언트 래퍼에 `try/except (redis.ConnectionError, redis.TimeoutError)` 안전 가드를 적용하여 Redis 다운 시 `Direct Model Call` 및 `Direct MySQL Query` 모드로 즉시 바이패스 전환.

### Rationale
- 캐시 서버의 일시적 장애가 전체 서비스 중단으로 이어지지 않는 무중단 복원력(Zero Downtime) 확보.
