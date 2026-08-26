# Quickstart & Validation Guide: 037-cross-service-llm-integration-and-citation-fix

**Branch**: `037-cross-service-llm-integration-and-citation-fix`  
**Date**: 2026-08-26  
**Status**: Completed  

---

## 1. Prerequisites

1. **Model Gateway running on port 8081**:
   - `GET http://127.0.0.1:8081/health` returns `200 OK`.
   - `GET http://127.0.0.1:8081/v1/profile` returns `current_model: "qwen3.5-2b"`, `current_n_ctx: 65536`.
2. **Embedding & Reranker Service running on port 8090**:
   - `POST http://127.0.0.1:8090/embeddings` returns 1024-dim vectors.
3. **MySQL & ChromaDB databases connected**:
   - Product catalog and reviews accessible.

---

## 2. Validation Scenarios

### Scenario 1: Complex Single Product Natural Language Query
**Target**: Verify entity decoupling and `[리뷰 N]` inline citation integrity.
- **Input**: `"컬러그램 탕후루 탱글 꿀로스의 발림성 장단점을 분석해줘"`
- **Expected Flow**:
  1. Router extracts `brand: "컬러그램"`, `product: "탕후루 탱글 꿀로스"`, `aspects: ["발림성", "장단점"]`.
  2. Search returns $>0$ reviews.
  3. Document Top-P ($P_{\text{doc}} \ge 0.85$) filters high-quality reviews.
  4. LLM outputs response containing `[리뷰 1]`, `[리뷰 2]` inline markers.
  5. UI expands `📚 참조 리뷰 원문` with matching snippets and ratings.

### Scenario 2: Category Discovery Recommendation Query
**Target**: Verify `FEATURE_DISCOVERY` auto-retrieval and namespace citation.
- **Input**: `"민감성 피부라 트러블 안나고 순하면서 붉은기 진정에 좋은 쿠션팩트 있나요"`
- **Expected Flow**:
  1. Router classifies intent as `FEATURE_DISCOVERY`, `category: "쿠션팩트"`, `aspects: ["민감성", "진정"]`.
  2. System retrieves top 3 rated cushion pacts and their top reviews.
  3. LLM outputs comparative recommendations with `[제품A 리뷰 1]`, `[제품B 리뷰 1]`.
  4. Zero hallucination (no "이 제품은...", no "안녕하세요? 순하고" gibberish).

### Scenario 3: Non-Existent Product Zero-Search Guard
**Target**: Verify 0-result hallucination elimination.
- **Input**: `"외계인 은하수 수분크림 발림성 알려줘"`
- **Expected Flow**:
  1. Search returns 0 reviews.
  2. Zero-Search Guard triggers `ZERO_SEARCH_TEMPLATE`.
  3. LLM politely informs that no verified Olive Young user reviews exist.
  4. 0 fake user quotes generated.

### Scenario 4: 2-Stage Top-P Verification
**Target**: Verify Document-Level Top-P and Token-Level Top-P.
- **Document Top-P**: Verify that when score cliff ($\Delta > 0.25$) occurs, low-scoring tail reviews are excluded.
- **Token Top-P**: Verify `top_p: 0.85` and `temperature: 0.3` are sent in client requests.

### Scenario 5: A-Team & B-Team Gateway Integration
**Target**: Verify cross-service gateway calls.
- **PILOS Report**: Executes batch analysis on 50 news items using `qwen3.5-4b` 32K mode.
- **ChatA / ChatB**: Executes streaming chat using `qwen3.5-2b` 64K mode (50+ TPS).

---

## 3. Automated Test Commands

```bash
# 1. B-Team Citation & Normalization Unit Tests
pytest bteam/Oliview_chatbot_a/tests/test_citation_integrity.py -v
pytest bteam/Oliview_chatbot_a/tests/test_entity_normalization.py -v
pytest bteam/Oliview_chatbot_a/tests/test_document_top_p.py -v

# 2. B-Team Discovery & Zero-Search Guard Tests
pytest bteam/Oliview_chatbot_b/tests/test_discovery_guard.py -v

# 3. Cross-Service Model Gateway Integration Tests
pytest model_gateway/tests/test_hardware_scaling_tiers.py -v
python bteam/Oliview_LLM/benchmark_gateway.py --runs 3

# 4. Full 7-Suite Regression Runner
python bteam/Oliview_LLM/run_all_regression_tests.py
```
