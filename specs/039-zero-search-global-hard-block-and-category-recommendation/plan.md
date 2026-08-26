# Implementation Plan: 039-zero-search-global-hard-block-and-category-recommendation

**Branch**: `039-zero-search-global-hard-block-and-category-recommendation` | **Date**: 2026-08-26 | **Spec**: [spec.md](./spec.md)  
**Constitution Version**: v1.1.1 Compliant

---

## Summary

본 피처는 ChatA(Streamlit, FastAPI) 및 ChatB(`project_ragapi.py`)에서 리뷰 선별 결과가 0건일 때 LLM이 26~33초 동안 "사용자 A/B/C" 가짜 리뷰를 창작하던 결함을 전면 해결합니다. 2026 CRAG Fast-Path (`should_abstain_zero_search`), DBMS 리뷰 보유 실존 상품 동적 인덱스(`DynamicCatalogIndex`), 속성 요약 뷰(`product_aspect_summaries`) 기반 카테고리 추천 RAG, 사후 근거 일치성 정제기(`GroundednessSanitizer`), 그리고 헌법 v1.1.1 기반 동적 환경 분리(`APP_RUN_MODE=DEMO/PRODUCTION`) 및 3개 `oliview_core` 단일 마스터 동기화를 구현합니다.

---

## Technical Context

**Language/Version**: Python 3.12 (uv package manager)  
**Primary Dependencies**: FastAPI 0.115+, Streamlit, LangGraph 0.2+, Pydantic 2.10+, PyMySQL 1.2+, ChromaDB 0.6+, BGE-M3 / BGE-Reranker  
**Storage**: MySQL 8.0+ (Relational / Aspects / Metadata), ChromaDB (`chroma.sqlite3`), Redis 7.0+ (L1/L4/L5 caching & SingleFlight locks)  
**Testing**: `pytest` (contract, unit, integration tests)  
**Target Platform**: Windows / Linux server with NVIDIA CUDA & Docker containers  
**Project Type**: Multi-Service AI RAG Pipeline & Web Application (ChatA & ChatB)  
**Performance Goals**:
- 제로 서치 즉시 기권(Abstention): $\le 3.0$초 (DEMO 모드) / $\le 0.5$초 (PRODUCTION 모드)
- 일반 다중 타겟 RAG: $\le 20.0$초 (DEMO 모드) / $\le 8.0$초 (PRODUCTION 모드)  
**Constraints**:
- 무환각 100% (0-reviews 시 가짜 후기 생성률 0.0%)
- 실존 리뷰 인라인 인용 부호(`[제품명 리뷰 N]`) 100% 결속
- 무하드코딩 원칙: `APP_RUN_MODE`(`.env`)를 통한 동적 주입  
**Scale/Scope**: 50,000+ Olive Young beauty reviews, 100+ brands, dual chat web interfaces

---

## Constitution Check

*GATE: Pre-Phase 0 & Post-Phase 1 verification.*

- [x] **Principle I (Language Policy)**: All user interactions, markdown docs, code comments, and zero-search templates in Korean.
- [x] **Principle II (TDD & Test-First)**: Red-Green-Refactor test cases specified in `tests/test_feature_039_zero_search.py`.
- [x] **Principle III (Service Modularity)**: `bteam/oliview_core` unified as single master; root legacy scripts quarantined to `legacy_archive/`.
- [x] **Principle IV (Observability)**: JSON structured logging for CRAG abstention and dynamic catalog lookups.
- [x] **Principle V (Simplicity & YAGNI)**: Reusing existing MySQL views, AST regex sanitizer, and LangGraph edges without unnecessary external frameworks.
- [x] **Principle VI (Dual Operating Modes & PoC Latency Tolerance)**: Injected dynamically via `APP_RUN_MODE` (`DEMO` / `PRODUCTION`) without hardcoding.

---

## Project Structure

### Documentation (this feature)

```text
specs/039-zero-search-global-hard-block-and-category-recommendation/
├── spec.md              # Feature specification
├── plan.md              # Implementation plan (this file)
├── research.md          # Phase 0 technical decisions
├── data-model.md        # Phase 1 data models & schemas
├── quickstart.md        # Verification & execution guide
├── contracts/           # Phase 1 JSON contracts
│   ├── zero_search_abstention_contract.json
│   ├── dynamic_catalog_index_contract.json
│   ├── groundedness_sanitizer_contract.json
│   └── sse_event_stream_contract.json
├── checklists/          # Requirements checklist
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks command)
```

### Source Code Architecture (bteam)

```text
bteam/
├── oliview_core/                            # [Master Core Package]
│   ├── config.py                            # Settings with APP_RUN_MODE (DEMO/PROD)
│   ├── db.py                                # MySQL connection & metadata queries
│   ├── graph_state.py                       # Extended RagGraphState
│   ├── graph_orchestrator.py                # LangGraph StateGraph with CRAG Abstention Edge
│   ├── guardrail.py                         # GroundednessSanitizer & Anti-Fictional Guard
│   ├── nodes/
│   │   ├── intent_node.py                   # Normalization with DynamicCatalogIndex
│   │   ├── search_node.py                   # Multi-Target & Aspect Hybrid Search
│   │   ├── reranker_node.py                 # Cross-Encoder Reranking
│   │   ├── abstention_node.py               # [NEW] 0.05s Zero-Search Abstention Node
│   │   ├── context_node.py                  # XML Sandbox Context Builder
│   │   └── synthesis_node.py                # Streamlit & API Streaming Node
│   └── tools/
│       ├── dynamic_catalog_index.py         # [NEW] In-memory review-bearing catalog index
│       └── search_tools.py                  # Hybrid & aspect search tools
├── sync_core.py                             # [NEW] Single-command master sync script
│
├── Oliview_chatbot_a/                       # [ChatA Application]
│   ├── app.py                               # Streamlit UI (Orchestrator unified)
│   ├── main.py                              # FastAPI SSE Server (Port 8000)
│   ├── oliview_core/                        # Synced with Master Core
│   ├── legacy_archive/                      # Quarantined legacy scripts
│   └── tests/                               # Test suite
│
└── Oliview_chatbot_b/                       # [ChatB Application]
    ├── project_ragapi.py                    # FastAPI SSE Server (Port 8001)
    ├── index.html                           # Vanilla JS Web UI
    ├── oliview_core/                        # Synced with Master Core
    ├── legacy_archive/                      # Quarantined legacy scripts
    └── tests/                               # Test suite
```

---

## Phase Breakdown

### Phase 0: Research (Completed)
- Resolved CRAG fast-path abstention mechanics.
- Defined MySQL review-bearing catalog query & `DynamicCatalogIndex`.
- Designed `GroundednessSanitizer` anti-fictional quote stripper.
- Verified Constitution v1.1.1 dynamic mode injection (`APP_RUN_MODE`).

### Phase 1: Design & Contracts (Completed)
- Created `data-model.md` for in-memory catalog, aspect aggregation, and state extensions.
- Created JSON schema contracts in `contracts/`.
- Created `quickstart.md` for testing & verification.

### Phase 2: Implementation Workflow (To be generated in `tasks.md`)
1. **P1 (Core TDD & Dynamic Index)**: Implement `dynamic_catalog_index.py`, `abstention_node.py`, and `GroundednessSanitizer` with comprehensive unit tests.
2. **P2 (CRAG LangGraph Integration)**: Wire `should_abstain_zero_search` edge into `graph_orchestrator.py` & `synthesis_node.py`.
3. **P3 (Aspect-Based Category Recommendation)**: Integrate `product_aspect_summaries` multi-target discovery.
4. **P4 (ChatA & ChatB Unification & Master Sync)**: Unify `app.py`, `project_ragapi.py`, run `sync_core.py`, and quarantine legacy root scripts to `legacy_archive/`.
