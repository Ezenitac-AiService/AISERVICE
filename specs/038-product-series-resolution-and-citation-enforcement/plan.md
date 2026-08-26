# Implementation Plan: 038-product-series-resolution-and-citation-enforcement (라인/시리즈명 모호성 해소, 화장품 부정 속성어 왜곡 방지, 0건 환각 차단 및 ChatA FastAPI 2026 모바일 반응형 웹 전환)

**Branch**: `038-product-series-resolution-and-citation-enforcement` | **Date**: 2026-08-26 | **Spec**: [spec.md](./spec.md)

---

## 1. Summary

본 계획서는 "헤라 센슈얼 립"과 같은 시리즈/라인명 질의 시 0건 검색 및 가짜 후기 환각이 발생하던 문제를 근본적으로 해결하기 위해,
1. **시리즈/서브브랜드 퍼지 카탈로그 확장 엔진**을 도입하여 실존 상품 2~3종을 자동 인출하고 비교 요약합니다.
2. **화장품 부정 속성 사전(`NEGATIVE_ASPECT_LEXICON`)**을 구축하여 "각질부각", "다크닝" 등의 단점 속성이 긍정 효과로 왜곡되는 현상을 원천 방지합니다.
3. **제로 서치 하드 블록(`ZERO_SEARCH_TEMPLATE`)**을 파이프라인 레벨에 강제하여 리뷰 0건 시 가짜 후기 창작을 100% 차단합니다.
4. **ChatA를 FastAPI 백엔드 + 모던 Vanilla Web으로 전환**하되, 데스크탑에서는 기존 ChatA의 2열 레이아웃을 100% 동일(Pixel-Identical)하게 재현하고, 모바일에서는 2026 웹 트렌드인 **Thumb-Zone**, **가로 스크롤 칩 필터**, **참조 리뷰 바텀 시트 드로어(Bottom Sheet)**를 구축합니다.

---

## 2. Technical Context

- **Language/Version**: Python 3.12+ (Backend) / HTML5, CSS3, ES6+ Vanilla JS (Frontend)
- **Primary Dependencies**: FastAPI, Uvicorn, LangGraph, Pydantic v2, ChromaDB, PyMySQL, KiwiPiePy, Redis
- **Storage**: MySQL (올리브영 상품 카탈로그/메타데이터), ChromaDB (리뷰 임베딩 벡터 DB), Redis (L1~L5 캐시)
- **Testing**: `pytest`, `pytest-asyncio`, `httpx` (TDD 기반 단위 및 통합 테스트)
- **Target Platform**: Windows Server / Linux Container, Modern Web Browsers (Chrome, Safari, Edge, Mobile Safari)
- **Project Type**: Web Application & RAG Multi-Agent System
- **Performance Goals**: 
  - 시리즈 퍼지 카탈로그 매칭 지연 시간 < 10ms
  - FastAPI SSE 최초 토큰 지연 시간 (TTFT) < 1.0s (캐시 적중 시 < 50ms)
  - '생성 중단' 클릭 시 클라이언트 렌더링 및 SSE 소켓 절단 < 100ms
- **Constraints**: 데스크탑 화면($\ge 768\text{px}$)에서 기존 Streamlit ChatA와의 시각적 일치성 100% 보장, 모바일 화면($< 768\text{px}$)에서 가로 스크롤 깨짐 0건

---

## 3. Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [X] **I. 언어 및 커뮤니케이션 정책 (Language Policy)**: 모든 문서, 계획서, 주석, UI는 한국어로 작성됨.
- [X] **II. TDD 및 테스트 우선주의 (Test-First & Contract Verification)**: 모든 신규 모듈(시리즈 매칭, 부정 속성 사전, 제로 서치, FastAPI 엔드포인트)에 대해 테스트를 선행 작성(Red-Green)함.
- [X] **III. 서비스 모듈화 및 격리 (Service Modularity)**: `bteam/Oliview_chatbot_a` 내에 FastAPI 서버 및 정적 웹 클라이언트를 독립 모듈로 배치.
- [X] **IV. 관측 가능성 및 로깅 (Observability)**: 파이프라인 단계별 JSON 구조화 로그 및 `trace_id` 일관 유지.
- [X] **V. 단순성 및 YAGNI (Simplicity)**: 무거운 Node.js 빌드 파이프라인 대신 순수 표준 웹(Vanilla JS/CSS)을 채택하여 복잡도 최소화.

---

## 4. Project Structure & Touch-points

### 4.1 Documentation (this feature)
```text
specs/038-product-series-resolution-and-citation-enforcement/
├── spec.md              # Feature specification
├── plan.md              # Implementation plan (this file)
├── research.md          # Architecture & technical decisions
├── data-model.md        # Data entities & schemas
├── contracts/           # API & UI Breakpoint contracts
│   └── api_contracts.md
├── quickstart.md        # Runnable validation guide
└── checklists/
    └── requirements.md  # Quality checklist
```

### 4.2 Source Code Touch-points
```text
bteam/Oliview_chatbot_a/
├── main.py                     # [NEW] FastAPI web server with SSE endpoint (/api/v1/chat/stream)
├── static/                     # [NEW] Pixel-Identical Vanilla Web Frontend
│   ├── index.html              # Desktop 2-Col + Mobile Bottom Sheet Responsive Layout
│   ├── css/
│   │   ├── style.css           # Pretendard, Olive Young Green (#2E9E44), Glassmorphism & Animations
│   │   └── mobile.css          # 2026 Mobile Responsive CSS (<768px, Thumb-Zone, Bottom Sheet)
│   └── js/
│       ├── app.js              # SSE client, AbortController, Bottom Sheet Drawer & Accordion
│       └── chat_ui.js          # Markdown renderer, [리뷰 N] badge click & highlight
├── oliview_core/
│   ├── utils/
│   │   └── entity_normalizer.py# [MODIFY] Series/sub-brand fuzzy matching & expansion
│   ├── tools/
│   │   └── search_tools.py     # [MODIFY] tool_search_catalog with substring series expansion
│   ├── nodes/
│   │   ├── router_node.py      # [MODIFY] Multi-target series expansion routing
│   │   ├── synthesis_node.py   # [MODIFY] Negative aspect prompt guard & Zero-Search Hard Block
│   │   └── rerank_node.py      # [MAINTAIN] Document Top-P 85% selection
│   └── guardrail.py            # [MODIFY] NEGATIVE_ASPECT_LEXICON validation guard
└── tests/
    ├── test_series_resolution.py       # [NEW] Test series matching (헤라 센슈얼 -> 누드 밤/글로스)
    ├── test_negative_aspect_guard.py   # [NEW] Test cosmetic negative lexicon guard (각질부각)
    ├── test_zero_search_hard_block.py  # [NEW] Test zero-search hard block
    └── test_fastapi_web_stream.py      # [NEW] Test FastAPI SSE streaming and AbortController
```

---

## 5. Implementation Phases

### Phase 1: Core NLP & Series Resolution (TDD)
1. Write `test_series_resolution.py` to verify series/line name fuzzy matching (`"헤라 센슈얼 립"` $\rightarrow$ `["헤라 센슈얼 누드 밤", "헤라 센슈얼 누드 글로스"]`).
2. Update `entity_normalizer.py` and `search_tools.py` with series expansion search.
3. Update `router_node.py` to auto-expand series queries into multi-target comparisons with `[제품명A 리뷰 N]` citations.

### Phase 2: Negative Aspect Lexicon & Zero-Search Hard Block (TDD)
1. Write `test_negative_aspect_guard.py` and `test_zero_search_hard_block.py`.
2. Implement `NEGATIVE_ASPECT_LEXICON` in `guardrail.py` and inject negative polarity constraints into `synthesis_node.py`.
3. Implement `ZERO_SEARCH_HARD_BLOCK` in `synthesis_node.py` to ensure 0-review cases never invoke LLM generation.

### Phase 3: FastAPI Web Server & Pixel-Identical Desktop UI
1. Create `bteam/Oliview_chatbot_a/main.py` with `/api/v1/chat/stream` SSE endpoint and static file mount.
2. Build `static/index.html`, `static/css/style.css`, and `static/js/app.js` replicating the exact Streamlit ChatA layout:
   - 2-Column top panel `[1.6:1.4]` (Brand/Category/Aspect chips + 1-Click Examples).
   - Real-time 4-Stage Status Box (`🔍 1. 의도 분석` $\rightarrow$ `📚 2. 하이브리드 검색` $\rightarrow$ `🏆 3. 리랭킹` $\rightarrow$ `✅ 완료`).
   - Grouped `📚 참조 리뷰 원문` accordion.
   - 1200px max-width backdrop-blur bottom fixed input bar.

### Phase 4: 2026 Mobile Responsive Layout & Bottom Sheet Drawer
1. Implement `static/css/mobile.css` for `@media (max-width: 768px)`:
   - Horizontal swipe category chip bar.
   - Thumb-Zone bottom bar with `visualViewport` & `env(safe-area-inset-bottom)`.
2. Implement interactive **Bottom Sheet Drawer** in `chat_ui.js` for mobile review preview when tapping `[리뷰 N]`.
3. Implement `AbortController` client-side Stop Generation (0ms).

### Phase 5: Verification & Full Regression
1. Execute unit and contract tests across `bteam/Oliview_chatbot_a/tests/`.
2. Run end-to-end quickstart scenarios in `quickstart.md`.
3. Synchronize `bteam/Oliview_chatbot_b/` with updated core modules.
