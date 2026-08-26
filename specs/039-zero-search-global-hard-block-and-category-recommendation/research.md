# Phase 0 Research & Technical Decision Document: Feature 039

**Feature**: `039-zero-search-global-hard-block-and-category-recommendation`  
**Created**: 2026-08-26  
**Status**: Completed  
**Goal**: Resolve all architectural questions, data modeling schemas, CRAG edge routing, and multi-tenant synchronizations.

---

## 1. Research Summary & Decisions

### Decision 1: 2026 CRAG Fast-Path Abstention & Pre-Synthesis Gate
- **Problem**: In both ChatA (`pipeline.py`, `app.py`) and ChatB (`project_ragapi.py`), when zero reviews are retrieved (`selected_review_count == 0` or `web_response_list == []`), the systems previously passed empty context to LLM `generate_stream()`, causing 26~33 seconds of fabricated "사용자 A, B, C" reviews.
- **Decision**: Introduce a deterministic LangGraph conditional routing edge `should_abstain_zero_search` immediately after the `RERANKING` node.
  - If `total_selected == 0`: Transition directly to `zero_search_abstention_node`.
  - `zero_search_abstention_node` streams `ZERO_SEARCH_TEMPLATE` + alternative recommendation chips in `<0.05s` (within DEMO SLA $\le 3.0$s / PROD SLA $\le 0.5$s) and emits `complete` event with `selected_review_count: 0`.
  - The heavy `LLM_SYNTHESIS` node is completely bypassed.

### Decision 2: DBMS Review-Bearing Dynamic Catalog Indexing (`DynamicCatalogIndex`)
- **Problem**: Static whitelists (6 brands) fail when new brands are crawled, while unfiltered DB queries include thousands of catalog items with 0 reviews, leading to empty retrievals and hallucination.
- **Decision**:
  - Implement `DynamicCatalogIndex` in `oliview_core/tools/dynamic_catalog_index.py`.
  - Server startup loads from MySQL view/query:
    ```sql
    SELECT p.product_id, p.product_name, p.brand_name, p.category, 
           COUNT(r.review_id) as review_count, AVG(r.rating) as avg_rating
    FROM products p
    INNER JOIN reviews r ON p.product_id = r.product_id
    GROUP BY p.product_id, p.product_name, p.brand_name, p.category
    HAVING review_count >= 1;
    ```
  - Builds in-memory:
    1. `active_brands: Set[str]` (normalized brand names)
    2. `active_products_by_category: Dict[str, List[ProductCatalogEntry]]`
    3. `product_lookup: Dict[str, ProductCatalogEntry]`
  - Query Normalization: If brand/product is out-of-index or has 0 reviews, flags state `is_out_of_catalog=True` in 0.1ms.

### Decision 3: Aspect-Based Recommendation Target Selection (`product_aspect_summaries`)
- **Problem**: For open-ended queries (e.g. "건성 피부에 촉촉하고 들뜸 없는 쿠션 추천해줘", "속건조 앰플"), blind vector search mixes tone/cream reviews or fails to find cushions with reviews.
- **Decision**:
  - For category/skin-type intent, query `product_aspect_summaries` (or fallback aggregation) with:
    - `category LIKE '%쿠션%'` OR `category LIKE '%앰플%'`
    - `total_review_count >= 5` (Small sample bias defense)
    - Ranked by `composite_score = positive_ratio * 0.7 + log(review_count) * 0.3`
  - Select top 2~3 verified real products as `target_entities` and route to Multi-Target Hybrid Search!

### Decision 4: Groundedness & Anti-Fictional-Review Sanitizer (`GroundednessSanitizer`)
- **Problem**: LLMs generate phrases like `"사용자 A"`, `"사용자 B"`, or unanchored quotes `"아침마다 얼굴이 촉촉해집니다"` when lacking evidence.
- **Decision**:
  - Add `GroundednessSanitizer` in `oliview_core/guardrail.py`.
  - System prompt strictly bans fictional placeholders ("사용자 A/B", "고객 1") and mandates `[제품명 리뷰 N]` tags.
  - Post-generation token/text parser inspects all quote blocks: any quote without an explicit `[제품명 리뷰 N]` anchor tag is stripped or converted to factual attribute summary.

### Decision 5: Dynamic Configuration (`APP_RUN_MODE=DEMO/PRODUCTION`) & Constitution Compliance
- **Problem**: Hardcoded timeouts or SLA limits break either in PoC demo environments on legacy hardware or in production.
- **Decision**:
  - Add `app_run_mode: AppRunMode = AppRunMode.DEMO` in `oliview_core/config.py` using Pydantic `BaseSettings`.
  - In `DEMO` mode: Zero-search SLA $\le 3.0$s, Regular RAG $\le 20.0$s.
  - In `PRODUCTION` mode: Zero-search SLA $\le 0.5$s, Regular RAG $\le 8.0$s.
  - Zero hardcoding; dynamic runtime resolution via `.env`.

### Decision 6: Multi-Tenant Single Master Core Synchronization
- **Problem**: `bteam/oliview_core`, `Oliview_chatbot_a/oliview_core`, and `Oliview_chatbot_b/oliview_core` had drift.
- **Decision**:
  - `bteam/oliview_core` is the Single Source of Truth Master.
  - Synchronization script `sync_core.py` ensures 100% byte-for-byte identical distribution to `Chat_a` and `Chat_b`.
  - Root legacy scratch scripts (`01_...`, `04.reranking.py`, `common.py`) quarantined into `legacy_archive/`.

---

## 2. Alternatives Considered & Rejection Rationale

| Option | Pros | Cons | Verdict |
|:---|:---|:---|:---|
| **A. Static Whitelist (6 brands)** | Simple | Cannot handle newly crawled brands or 0-review items in catalog | ❌ Rejected |
| **B. Real-time SQL on Every Token** | Always fresh | MySQL connection pool exhaustion under load | ❌ Rejected |
| **C. In-Memory Dynamic Index + CRAG Gate (Chosen)** | Sub-millisecond check, 0 DB load per request, 100% zero-hallucination | Requires startup preload (~50ms) | 🟢 **Adopted** |
| **D. Post-hoc LLM Hallucination Judge** | High flexibility | High latency (adds 3~5s) and token cost | ❌ Rejected for Fast Path |
| **E. AST/Regex Groundedness Sanitizer (Chosen)** | Zero latency (<1ms), deterministic enforcement | Requires strict prompt citation syntax | 🟢 **Adopted** |
