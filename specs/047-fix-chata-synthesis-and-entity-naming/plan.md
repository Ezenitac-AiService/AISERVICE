# Implementation Plan: 047-fix-chata-synthesis-and-entity-naming

**Branch**: `047-fix-chata-synthesis-and-entity-naming` | **Date**: 2026-09-02 | **Spec**: [`spec.md`](file:///c:/AISERVICE/specs/047-fix-chata-synthesis-and-entity-naming/spec.md)

**Input**: Feature specification from `/specs/047-fix-chata-synthesis-and-entity-naming/spec.md`

---

## 1. Summary

올리뷰 챗봇(ChatA, ChatB)에서 발생하는 4대 핵심 정합성 및 런타임 결함(1. 카테고리/추천 질의 시 질문 문장으로 상품명이 왜곡되는 결함, 2. LLM 합성 타임아웃 오류, 3. 에러 메시지가 Redis L5 캐시에 영구 고착되는 캐시 오염 결함, 4. 리뷰 본문 내 선행 대괄호 잔여물 노출)을 해결하기 위해, **의도 라우터-검색 풀-인용 바인딩-LLM 스트리밍-L5 캐시 게이트-텍스트 전처리에 이르는 RAG 코어 전 계층을 전면 정비하고 공용 마스터 코어(`bteam/oliview_core`)를 기준으로 3-Way 동기화**한다.

---

## 2. Technical Context

- **Language/Version**: Python 3.12 (uv package manager / FastAPI / Uvicorn)
- **Primary Dependencies**: `langgraph>=0.2.76`, `fastapi>=0.111.0`, `uvicorn>=0.30.0`, `httpx>=0.28.1`, `sse-starlette>=2.0.0`, `redis>=5.0.0`, `chromadb>=0.5.0`
- **Storage**: MySQL (`bteam_db`), Redis 7 (`aiservice-redis`), ChromaDB Vector Index
- **Testing**: `pytest` (Asyncio, AnyIO) with 100% regression test pass requirement
- **Target Platform**: Docker Compose / Linux / Windows WSL2 / Nginx Gateway
- **Project Type**: Distributed Agentic RAG Microservice
- **Performance Goals**:
  - 카테고리 발굴 및 다중 타겟 RAG 응답 스트리밍 완주: DEMO 모드 $\le 20.0$초 (헌법 제6조)
  - L5 캐시 히트 시 즉시 응답: $\le 0.2$초
- **Constraints**:
  - 제로 서치 및 카테고리 발굴 시 100% 무환각 및 실존 리뷰 결속 (헌법 제6조)
  - 포괄적 무하드코딩 및 환경 변수 SSOT 원칙 준수 (헌법 제7조)
  - 에러 문자열 L5 캐시 저장 0% (OWASP LLM08 Cache Poisoning 방어)

---

## 3. Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle I (Language & Communication)**: 사용자 대화, 산출물(명세서, 계획서, 주석) 한국어 작성 준수 (`PASS`)
- **Principle II (Test-First & Contract Verification)**: 단위/통합 테스트 선행 및 100% 통과 검증 준수 (`PASS`)
- **Principle III (Service Modularity & Environment Isolation)**: 마스터 코어(`bteam/oliview_core`) 중심의 3-Way 동기화(`sync_core.py`)로 격리 보존 (`PASS`)
- **Principle IV (Observability & Structured Logging)**: JSON 구조화 로깅(`trace_id`, `step_id`, `latency_ms`) 유지 (`PASS`)
- **Principle V (Simplicity & YAGNI)**: 복잡한 외부 의존성 추가 없이 순수 파이프라인 정제 중심 구현 (`PASS`)
- **Principle VI (Dual Operating Modes & PoC Latency Tolerance)**: `APP_RUN_MODE=DEMO` 기준 180s 타임아웃 완화 및 무환각 원칙 준수 (`PASS`)
- **Principle VII (Zero Hardcoding & Infrastructure SSOT)**: 모든 타임아웃, 포트, URL을 `config.py` Settings 객체로 일원화 (`PASS`)

---

## 4. Project Structure

### Documentation (this feature)

```text
specs/047-fix-chata-synthesis-and-entity-naming/
├── spec.md              # Feature specification
├── plan.md              # Implementation plan
├── research.md          # Phase 0: Technical decisions & research
├── data-model.md        # Phase 1: Entity schemas & validation rules
├── quickstart.md        # Phase 1: Validation & execution guide
├── contracts/           # Phase 1: Interface & SSE stream contracts
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code Layout

```text
bteam/
├── oliview_core/                        # [MASTER CORE SSOT]
│   ├── client.py                        # LLM/Reranker/Embeddings HTTP client (180s timeout)
│   ├── config.py                        # Centralized configuration & timeout settings
│   ├── graph_orchestrator.py            # LangGraph multi-target RAG orchestrator & URL builder
│   ├── sanitizer.py                     # Review text cleaner (bracket & category stripper)
│   ├── utils/
│   │   └── document_top_p.py            # Document Top-P citation tag generator
│   └── nodes/
│       ├── router_node.py               # Intent & entity normalization (discovery decoupling)
│       ├── search_node.py               # Hybrid search node (bound to DB product_name)
│       ├── rerank_node.py               # Document Top-P reranker node (dynamic grouping)
│       ├── context_node.py              # 3-Tier context assembler
│       └── synthesis_node.py            # LLM streaming & Gated L5 Cache Poison Defense
├── Oliview_chatbot_a/                   # [CHAT A - FastAPI]
│   └── oliview_core/                    # Synchronized from master
├── Oliview_chatbot_b/                   # [CHAT B - FastAPI / Playground]
│   └── oliview_core/                    # Synchronized from master
└── sync_core.py                         # 3-Way core synchronization utility
```

---

## 5. Implementation Phases & Work Breakdown

### Phase 0: Research & Grounding (Completed)
- 2026 Agentic RAG 표준, LangGraph SubGraph 상태 격리, L5 Cache Poison Defense, vLLM Streaming Timeout 연구 및 `research.md` 작성.

### Phase 1: Design & Schema Contracts (Completed)
- `data-model.md`, `contracts/rag-core-contracts.md`, `quickstart.md`, `plan.md` 작성 완료.

### Phase 2: TDD Test Construction (Task Generation Prep)
- `test_entity_naming_discovery.py`: 카테고리 발굴 질의 시 질문 문장이 상품명으로 오염되지 않는지 검증하는 단위 테스트.
- `test_l5_cache_poison_gate.py`: 에러 토큰 발생 시 L5 캐시 저장이 100% 차단되는지 검증하는 단위 테스트.
- `test_sanitizer_bracket_stripper.py`: 닫는 괄호(`]`) 및 선행 태그 잔여물이 깨끗이 정제되는지 검증하는 단위 테스트.
- `test_client_resilient_timeout.py`: 완화된 180s 타임아웃 및 SSE 파서 회귀 테스트.

### Phase 3: Core Implementation & Master Synchronization
- `bteam/oliview_core` 내 `router_node.py`, `search_node.py`, `document_top_p.py`, `graph_orchestrator.py`, `synthesis_node.py`, `client.py`, `sanitizer.py`, `config.py` 수정.
- `python bteam/sync_core.py` 실행하여 ChatA 및 ChatB로 100% 바이트 동일 동기화.

### Phase 4: Verification & Live Docker Container Validation
- 49개 전수 테스트 통과 확인.
- 실시간 Live 질의(*"스킨케어에서 수분감 좋은 인기 앰플 추천해줘"*, *"여름철 기름기 잡고 모공 커버 매트 파운데이션"*) 검증.
