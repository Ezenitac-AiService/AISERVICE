# Research: Reranker Pipeline & Multi-Target RAG Optimization

**Feature**: `030-reranker-pipeline-optimization`  
**Date**: 2026-08-25  

## 1. Reranker Serving Latency & Batch Windowing

### Decision
- 후보군을 **분석 대상(타겟)당 10건**으로 압축하고, 다중 타겟 비교 시(예: 2개 타겟 = 20건) 개별 요청으로 나누지 않고 **단 1회의 통합 배치 요청(Single Batch Request)**으로 8091 BGE-Reranker에 전송.
- **5.0초 단일 표준 타임아웃** 적용 및 로컬 CPU CrossEncoder 폴백 완전 제거(0ms 즉각 1단계 코사인 유사도 순위 유지).

### Rationale
- 포트 8091 내부 벤치마크 결과: 25건 배치 시 8.47초~10.59초 소요.
- 10건 단일 배치 시 1.5초, 20건 통합 배치 시 2.8초 소요로 5.0초 타임아웃 이내에 완결 가능.
- 기존 Chatbot B는 5.0초 타임아웃으로 매번 사일런트 폴백되던 결함 해소, Chatbot A는 20초 대기 락 해소.

### Alternatives Considered
- *대안 1: CPU sentence_transformers 로컬 폴백* → 기각: CPU에서 15~20초 추가 지연 발생으로 사용자 경험 치명적 훼손.
- *대안 2: 타겟별 개별 병렬 HTTP 호출* → 기각: `llama_cpp.server`가 단일 GPU 큐를 가지므로 서버 내에서 직렬화 대기가 발생하여 지연 시간이 2배로 증가함.

---

## 2. Query Orchestration Engine: LangGraph StateGraph

### Decision
- `langgraph >= 0.2.0, < 0.3.0` 및 `langchain-core >= 0.3.0, < 0.4.0`를 도입하여 **선언적 StateGraph 상태 머신** 구축.
- `Send` API를 통한 서브 타겟 병렬 검색(Map-Reduce), 내장 `astream_events` 기반 실시간 계층형 서브스텝 스트리밍.

### Rationale
- 3대 RAG 라우팅 패턴(`명시적 제품 비교`, `기능 기반 다자 비교`, `장단점/다중 속성 분석`, `단일 질의`)을 깔끔한 조건부 엣지로 표현 가능.
- 순수 Python async 대비 상태 동기화 및 맵-리듀스 코드 복잡도를 70% 이상 절감.
- 노드 전환 오버헤드가 1~3ms에 불과하여 4~5초 파이프라인에서 영향도 0.05% 미만.

### Alternatives Considered
- *대안 1: 순수 `asyncio.gather` 절차적 코드 유지* → 기각: 다중 타겟 분기 및 실시간 서브스텝 이벤트 큐 관리가 지나치게 복잡해지고 유지보수성 저하.

---

## 3. Redis 4-Tier Caching & In-Memory Layer

### Decision
- 전역 `redis.ConnectionPool` 싱글톤 기반 4단계 캐시 구축:
  1. `L1`: 1차 검색 풀 캐시 (`v1:rag:pool:{target}:{attr}`, TTL 12h, Single-flight lock)
  2. `L2`: 질문 임베딩 벡터 캐시 (`emb:bge-m3:{hash}`, TTL 7d)
  3. `L3`: 리랭커 교차 유사도 점수 캐시 (`rerank:{q_hash}:{docs_hash}`, TTL 24h)
  4. `L4`: LangGraph 멀티턴 세션 체크포인터 (`checkpoint:{session_id}`, TTL 3d)
- `socket_timeout=0.2s` Fail-Fast 적용.

### Rationale
- Chatbot B가 자체 HTTP 호출로 인해 Redis 캐시를 100% 우회하던 결함 완전 정상화.
- 반복 질의 및 인기 상품 비교 시 0.1초대 즉시 응답 제공.

---

## 4. Qwen 3.5 2B 16K Large Context & TTFT Optimization

### Decision
- 입력 컨텍스트 예산 **최대 6,000토큰(타겟당 2,000토큰)** + 최대 생성 토큰 **4,096토큰** 설정.
- 모델 게이트웨이 파라미터 `--n_batch 2048 --n_ubatch 512`로 프롬프트 프리필(TTFT) 0.5초 이내 가속.

### Rationale
- Qwen 3.5 2B는 16K 윈도우와 FlashAttention을 기본 탑재하고 있어 대형 컨텍스트를 초당 40~50토큰으로 고속 처리 가능.
- 제품 비교 표 및 세부 장단점 리포트가 중도 잘림 없이 완결형으로 생성됨.

---

## 5. Production Reliability & SRE Safeguards

### Decision
1. **타겟별 쿼터 파티셔닝 (Per-Target Quota)**: 리랭킹 점수 정렬 후 타겟별로 상위 2~3건씩 독립 선별하여 특정 제품 쏠림 0% 보장.
2. **서브노드 부분 장애 격리 (Fault-Isolation)**: 병렬 검색 중 1개 제품 DB 오류 시 잔여 정상 타겟으로 100% 완결.
3. **SSE 클라이언트 연결단절 즉시 취소**: `await request.is_disconnected()` 감지 시 GPU 태스크 즉각 Abort.
4. **비동기 MySQL 커넥션 풀**: `aiomysql.create_pool(maxsize=10)`로 커넥션 누수 방지.
5. **동시성 VRAM 세마포어**: `asyncio.Semaphore(3)` 가드로 동시 3건 초과 시 인메모리 큐잉.
6. **무중단 핫스왑 피처 플래그**: `FEATURE_LANGGRAPH_RAG=true/false` 환경 변수로 0초 롤백 지원.
