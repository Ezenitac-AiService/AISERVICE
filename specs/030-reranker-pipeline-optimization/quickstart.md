# Quickstart Validation Guide: 030-reranker-pipeline-optimization

**Feature**: `030-reranker-pipeline-optimization`  
**Date**: 2026-08-25  

## 1. Prerequisites

1. Docker 컨테이너 정상 가동 확인:
   - `aiservice-redis` (Port 6379)
   - `vllm-serv-gateway` (Port 8081 LLM, 8090 Embedding, 8091 Reranker)
   - `aiservice-mysql` (Port 3306)

---

## 2. Automated Test Suite Execution

### 2.1. 단위 및 계약 테스트 (Unit & Contract Tests)
```bash
# oliview_core 단위 및 계약 테스트 실행
docker exec -it oliview-streamlit pytest /app/tests/unit/test_graph_orchestrator.py -v
docker exec -it oliview-streamlit pytest /app/tests/unit/test_redis_cache_4tier.py -v
docker exec -it oliview-streamlit pytest /app/tests/unit/test_reranker_single_batch.py -v
```

### 2.2. A/B 챗봇 E2E 정합성 및 레이턴시 벤치마크
```bash
# 10개 대표 질의(단일/다중/장단점) E2E 벤치마크 실행
python scratch/benchmark_rag_orchestrator.py
```

---

## 3. Manual Scenario Verification

### Scenario 1: 명시적 2개 제품 비교 질의
1. Chatbot A(Streamlit: `http://localhost:8501`) 또는 Chatbot B(FastAPI: `http://localhost:8000`) 접속.
2. 질문 입력: `"차앤박 프로폴리스 앰플이랑 식물나라 시카 토너 수분감 비교해줘"`
3. **검증 포인트**:
   - 실시간 타임라인에 `[1/2] 차앤박 앰플 검색 완료 (10건)`, `[2/2] 식물나라 토너 검색 완료 (10건)`이 순차 렌더링되는가?
   - 전처리(검색+리랭킹)가 3.0초 이내에 완료되는가?
   - 답변 인용에 두 제품의 리뷰가 각각 3건씩 공정하게 인용되고 스펙 비교표가 제공되는가?

### Scenario 2: 리랭커 타임아웃 주입 및 안전 폴백 UX
1. 8091 리랭커에 인위적 6초 지연 주입 또는 중단.
2. 질문 입력: `"헤라 블랙쿠션 장단점 알려줘"`
3. **검증 포인트**:
   - 5.0초 도달 즉시 중단 없이 답변 스트리밍이 시작되는가?
   - 상태창에 `"⚡ 신속 분석 모드 (실시간 기본 검색)"` 배지가 정상 표시되는가?

### Scenario 3: Redis 2회차 캐시 히트 0.1초 검증
1. 동일 질문을 재입력.
2. **검증 포인트**:
   - 전처리 지연 시간이 10ms 이내로 측정되고 0.2초 이내에 토큰 생성이 시작되는가?
