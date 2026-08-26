# Implementation Plan: Spec 035 - Agentic AI Architecture, Harness Engineering & Dynamic Context Window Expansion

**Branch**: `035-service-context-window-expansion` | **Date**: 2026-08-26 | **Spec**: [`spec.md`](file:///c:/AISERVICE/specs/035-service-context-window-expansion/spec.md)

---

## Summary

본 계획서는 모델 게이트웨이의 16K~32K+ 대용량 컨텍스트 윈도우(Spec 034)를 각 클라이언트 서비스(`bteam/oliview_core`, `ChatA`, `ChatB`, `ateam/pilos`)가 100% 활용할 수 있도록, **(1) 절차형 파이프라인을 진정한 LangGraph `Compiled StateGraph`로 승격**, **(2) 3-Tier `Context & Execution Harness` 구축**, **(3) Self-RAG 검색 품질 검증 및 하이브리드 재검색 루프 구축**, **(4) 계층형 메모리 및 암묵적 지시어(Anaphora) Redis 온디맨드 심층 회상(Deep Recall)**, **(5) 2026 트렌드 기반 `Living Agent Inspector` 동적 DAG UI 시각화**를 구현하기 위한 실행 계획입니다.

---

## Technical Context

- **Language/Version**: Python 3.11+ / ES6+ JavaScript
- **Primary Frameworks**: LangGraph v0.2+, FastAPI, PyNVML, Redis 7.x, ChromaDB, BGE-M3, BGE-Reranker-v2-m3
- **Storage/Cache**: Redis (L1 검색 풀, L2 임베딩, L3 리랭킹, L4 세션/체크포인트, L5 응답 캐시), MySQL, ChromaDB Vector DB
- **Testing Tools**: pytest, pytest-asyncio, unittest, requests
- **Target Platform**: Docker Compose / Linux (Ubuntu 22.04) / NVIDIA GPU (GTX 1070 8GB ~ RTX 4080 16GB)
- **Project Type**: Microservices Multi-Agent AI System
- **Performance Targets**: 
  - 16K 대용량 컨텍스트 TTFT < 2.5s (L5 캐시 히트 시 < 50ms)
  - Redis Deep Recall 조회 지연시간 < 2ms
  - Self-RAG 재검색 루프 최대 1회 한정 (지연시간 폭증 방어)
- **Constraints**: 
  - 프롬프트 안전 마진: 총 토큰이 유효 컨텍스트의 85%를 초과하지 않도록 `PreFlightContextGuard` 필수
  - 무중단 호환성: 기존 API 엔드포인트 및 단일 질의 포맷 완벽 호환

---

## Constitution Check

*GATE: All items must pass before Phase 2 implementation.*

- [x] **I. 언어 및 커뮤니케이션 정책**: 모든 대화, 문서, 주석, 오류 메시지 한국어 원칙 준수.
- [x] **II. TDD 및 테스트 우선주의**: `CompiledStateGraph`, `QualityGate`, `DeepRecall` 단위/통합 테스트 선행 작성.
- [x] **III. 서비스 모듈화 및 격리**: `bteam/oliview_core`와 `ateam/pilos`의 독립적 실행 및 컨테이너 격리 보장.
- [x] **IV. 관측 가능성 및 구조화된 로깅**: StepTimer, TraceID, Living Inspector SSE 이벤트 로깅 표준 준수.
- [x] **V. 단순성 및 점진적 진화**: 무한 루프 차단(최대 1회), YAGNI 원칙에 입각한 계층형 슬라이딩 윈도우.

---

## Project Structure & Target Files

```text
c:\AISERVICE\
├── bteam\
│   ├── oliview_core\
│   │   ├── config.py                 # [MODIFY] 3-Tier ContextHarnessProfile & 동적 예산
│   │   ├── graph_state.py            # [MODIFY] RagGraphState & LivingInspectorEvent 스키마
│   │   ├── graph_orchestrator.py     # [REFACTOR] True Compiled StateGraph & 조건부 엣지
│   │   ├── nodes\
│   │   │   ├── router_node.py        # [MODIFY] 의도 및 Anaphora 지시어 1차 분석
│   │   │   ├── search_node.py        # [MODIFY] 3-Tier 후보 풀 크기 확장
│   │   │   ├── rerank_node.py        # [MODIFY] 타겟당 리뷰 동적 쿼터 선별 (5~15개)
│   │   │   ├── quality_grade_node.py # [NEW] Self-RAG 검색 품질 검증 노드
│   │   │   ├── reformulation_node.py # [NEW] 하이브리드(사전+Fast LLM) 쿼리 재작성 노드
│   │   │   ├── deep_recall_node.py   # [NEW] Redis L4 온디맨드 세션 원본 역조회 노드
│   │   │   ├── context_node.py       # [MODIFY] 16K/32K 고밀도 XML 샌드박스 패키징
│   │   │   └── synthesis_node.py     # [MODIFY] 확장된 생성 토큰(3K~4K) 수용
│   │   ├── session.py                # [MODIFY] 계층형 메모리 요약 & AnaphoraTurnMap
│   │   └── anaphora_resolver.py      # [MODIFY] 3단계 암묵적 지시어 해석 엔진
│   ├── Oliview_chatbot_b\
│   │   └── index.html                # [MODIFY] Living Agent Inspector 동적 DAG 렌더러
│   └── tests\
│       ├── test_compiled_stategraph.py     # [NEW] LangGraph 컴파일드 그래프 검증
│       ├── test_self_rag_quality_gate.py   # [NEW] Self-RAG 품질 판정 및 루프 검증
│       ├── test_anaphora_deep_recall.py    # [NEW] 암묵적 역참조 및 Redis 복원 검증
│       └── test_dynamic_context_harness.py # [NEW] 16K/32K 예산 분배기 검증
└── ateam\
    └── pilos-sentiment-index\
        ├── pilos\collection\ai_clients\
        │   └── llm_report_client.py  # [MODIFY] PilosExecutionHarness (30~60건 일괄 주입)
        └── tests\
            └── test_llm_report_harness.py # [NEW] 대용량 리포트 일괄 주입 테스트
```

---

## Phases & Implementation Milestones

### Phase 1: Context Harness & Data Model Schemas
- `bteam/oliview_core/config.py`: `ContextHarnessProfile` 및 3-Tier (16K/32K/64K+) 동적 산정 로직 구현.
- `bteam/oliview_core/graph_state.py`: `QualityGradeVerdict`, `LivingInspectorEvent`, `DeepRecallTurnPayload` Pydantic 모델 정의.

### Phase 2: True Compiled StateGraph & Node Modularization
- `bteam/oliview_core/nodes/quality_grade_node.py`: 1차 검색 관련성 점수 평가 노드 작성.
- `bteam/oliview_core/nodes/reformulation_node.py`: 동의어 사전 + Fast LLM 문맥 재작성 하이브리드 노드 작성.
- `bteam/oliview_core/nodes/deep_recall_node.py`: Redis L4 세션 스토어 역조회 노드 작성.
- `bteam/oliview_core/graph_orchestrator.py`: `langgraph.graph.StateGraph` 인스턴스화, `add_node`, `add_conditional_edges`, `compile()` 및 `astream_events` 기반 비동기 파이프라인 구현.

### Phase 3: Large Context XML Packaging & Anaphora Resolution
- `bteam/oliview_core/nodes/context_node.py`: 16K (10,000토큰) / 32K (22,000토큰) XML 샌드박스 컨텍스트 빌더 확장.
- `bteam/oliview_core/nodes/rerank_node.py`: 타겟당 5~15개 리뷰 동적 쿼터 선별.
- `bteam/oliview_core/session.py` & `anaphora_resolver.py`: `[Turn N]` 메타데이터 태그 및 세션 내 BGE 임베딩 코사인 유사도 검색 구현.

### Phase 4: Living Agent Inspector Frontend Integration
- `bteam/Oliview_chatbot_b/index.html` & ChatA: 정적 4단계 배열 제거, `LivingInspectorEvent` 실시간 DOM 동적 삽입, 서브 브랜치 들여쓰기(`↳ 🔄`), 마이크로 텔레메트리 뱃지 및 첫 토큰 수신 시 Auto-Collapse 구현.

### Phase 5: PILOS Batch Report Execution Harness
- `ateam/pilos-sentiment-index/pilos/collection/ai_clients/llm_report_client.py`: 30~60건 뉴스 기사 일괄 주입 `PilosExecutionHarness` 및 Pre-flight Guard 연동.

### Phase 6: E2E Verification & Evaluation Benchmark
- `bteam/tests/`: 4개 신규 TDD 테스트 스위트 실행 및 통과 검증.
- `ateam/tests/`: PILOS 50건 대용량 리포트 벤치마크 실행 및 검증.
- 라이브 컨테이너 16K/32K 다중 비교 질의 실측 검증.
