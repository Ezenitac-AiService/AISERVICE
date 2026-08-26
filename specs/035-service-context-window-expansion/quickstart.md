# Quickstart Validation Guide: Spec 035

**Feature Title**: Agentic AI Architecture, Harness Engineering, Living Process Inspector & Dynamic Context Window (16K/32K+) Expansion  
**Date**: 2026-08-26  
**Status**: 100% Verified & Fully Operational

---

## 1. Prerequisites & Environment Check

```bash
# 1. 도커 컨테이너 가동 상태 확인
docker compose ps

# 2. 게이트웨이 유효 컨텍스트 및 모델 프로파일 확인
curl -s http://127.0.0.1:8081/v1/profile | jq .
```

---

## 2. End-to-End Test Scenarios & Verified Results

### 시나리오 1: 16K/32K 대용량 다중 제품 비교 & Living Inspector 검증
* **목적**: 16K 컨텍스트에서 10개 이상의 리뷰가 주입되고, UI에 동적 StateGraph 노드와 서브 브랜치가 실시간 렌더링되는지 검증.
* **실행 명령**:
  ```bash
  docker compose exec -T oliview_chatbot_b python tests/run_all_regression_tests.py
  ```
* **검증 결과 (Live Verified)**:
  - `CompiledStateGraph` 정상 실행 (`INTENT` ➔ `SEARCH` ➔ `RERANK` ➔ `QUALITY_GRADE` ➔ `CONTEXT_BUILD` ➔ `SYNTHESIS`).
  - 8개 동적 노드 및 서브스텝 이벤트 실시간 방출.
  - 16K Baseline (10,000 max input tokens, 2,048 output tokens) 정상 할당 확인.

---

### 시나리오 2: Self-RAG 품질 검증 및 하이브리드 재검색 루프
* **목적**: 1차 검색 품질 미달 시 `QualityGradeNode` ➔ `HybridQueryReformulation` 분기가 1회 정상 발동하는지 검증.
* **검증 결과 (Live Verified)**:
  - `QualityGradeVerdict.status == "RETRY_SEARCH"` (평균 점수 < 0.35 감지).
  - 동의어 사전(`ALIAS_DICTIONARY`) + Fast LLM 문맥 쿼리 병합 실행 (`↳ 🔄 하이브리드 재검색 중`).
  - 루프 가드(`retry_count <= 1`)에 의해 1회 재검색 후 `CONTEXT_BUILD`로 반드시 종결.

---

### 시나리오 3: 암묵적 지시어(Anaphora) & Redis On-Demand Deep Recall
* **목적**: 15턴 이전의 과거 대화에 대해 "아까 그 크림" 질문 시 Redis L4에서 원본 스펙이 복원 주입되는지 검증.
* **검증 결과 (Live Verified)**:
  - `AnaphoraResolver` 3단계 파이프라인 (Rule ➔ BGE Cosine Similarity ➔ Fallback)으로 Turn 7 특정.
  - Redis L4 세션 스토어(`session:{id}:turn:7`)에서 원본 스펙/리뷰를 온디맨드 복원하여 `<recalled_context>`로 프롬프트에 주입.

---

### 시나리오 4: PILOS 50건 뉴스 대용량 일괄 감성 분석
* **목적**: 50건의 뉴스 기사를 단일 프롬프트에 주입하여 Truncation 에러 없이 종합 감성 지수가 도출되는지 검증.
* **실행 명령**:
  ```bash
  docker compose exec -T pilos_web python -m unittest tests/test_llm_report_harness.py
  ```
* **검증 결과 (Live Verified)**:
  - `<market_documents total_count="50">` XML 번들링 정상 완료.
  - `PilosExecutionHarness` 2048 토큰 예산 확장 및 단위 테스트 `OK (1 test in 0.000s)`.

---

## 3. Full Regression Suite Summary

```text
================================================================
   🧪 OLIVIEW CORE SPEC 035 AGENTIC REGRESSION TEST SUITE 🧪   
================================================================

[1/7] Security & Prompt Injection Guardrails Regression (Spec 021 / 022)...
  ✅ Security & Guardrails: 3/3 Tests Passed!

[2/7] 3-Tier Dynamic Context Harness & PreFlight Guard (Spec 035)...
  ✅ 3-Tier Context Harness & PreFlight Guard: Passed!

[3/7] Self-RAG Quality Gate & Hybrid Reformulation (Spec 035)...
  ✅ Self-RAG Quality Gate & Hybrid Reformulation: Passed!

[4/7] Implicit Anaphora Resolution & Deep Recall (Spec 035)...
  ✅ Implicit Anaphora Resolution: Passed!

[5/7] Intent Router & Pattern Classification (Spec 030)...
  ✅ Intent Router: Passed!

[6/7] L5 Caching & SingleFlight Lock (Spec 032)...
  ✅ L5 Core & SingleFlight: Passed!

[7/7] E2E StateGraph & Living Inspector Events (Spec 035)...
  ✅ E2E StateGraph & Living Inspector: 8 Nodes rendered, tokens streamed!

================================================================
   🎉 ALL 7 SPEC 035 REGRESSION TEST SUITES PASSED (100%) 🎉   
================================================================
```
