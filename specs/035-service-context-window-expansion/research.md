# Research & Technology Evaluation: Spec 035

**Feature Title**: Agentic AI Architecture, Harness Engineering, Living Process Inspector & Dynamic Context Window (16K/32K+) Expansion  
**Date**: 2026-08-26  
**Status**: Completed

---

## 1. Research Questions & Technology Decisions

### D1. True LangGraph `Compiled StateGraph` vs Procedural Wrapper
- **Decision**: `bteam/oliview_core/graph_orchestrator.py`의 절차형 함수 순차 호출을 전면 폐지하고, `langgraph.graph.StateGraph` 기반의 컴파일된 그래프(`compile()`)로 전면 전환.
- **Rationale**:
  - 기존 절차형 코드는 조건부 분기(Conditional Branching), 재검색 루프(Self-RAG Loop), 에이전트 상태 복원(Checkpointing)이 불가능하여 무늬만 LangGraph인 기술 부채 상태였음.
  - LangGraph v0.2+의 `StateGraph`에 `add_node()`, `add_edge()`, `add_conditional_edges()`를 선언하고, `astream_events(version="v2")` 및 `dispatch_custom_event()`를 통해 노드 실행 이벤트를 비동기 스트리밍함.
- **Alternatives Considered**:
  - *LlamaIndex Workflow*: 프로젝트의 기존 베이스라인이 LangGraph 기반으로 선언되어 있어 스택 변경 오버헤드가 큼.
  - *순수 Python 비동기 큐*: 상태 전이 추적 및 향후 Multi-Agent 확장 시 복잡도가 기하급수적으로 증가함.

---

### D2. 3-Tier Agentic Context Harness (16K / 32K / 64K+)
- **Decision**: 게이트웨이의 `GET /v1/models` 및 `GET /v1/profile`에서 실시간 유효 컨텍스트 크기(`current_n_ctx`, `dynamic_n_ctx_max`)를 감지하여 3단계 예산 정책을 산정하는 `ContextHarness` 구현.
- **Rationale**:
  - **Tier 1 (16K Baseline, 16,384 tokens)**: 입력 컨텍스트 최대 10,000토큰, 타겟당 리뷰 5~8개 선별, 타겟당 3,500토큰, 대화 히스토리 15턴, 최대 생성 2,048~3,072토큰.
  - **Tier 2 (32K Standard, 32,768 tokens)**: 입력 컨텍스트 최대 22,000토큰, 타겟당 리뷰 10~15개 선별, 타겟당 7,000토큰, 대화 히스토리 30턴, 최대 생성 4,096토큰.
  - **Tier 3 (64K~128K Ultra, 65K~131K tokens)**: 입력 컨텍스트 최대 48,000~96,000토큰, 타겟당 리뷰 20개+, 최대 생성 8,192토큰.
  - 프롬프트 안전 마진: 총 토큰이 유효 컨텍스트의 85%를 초과하지 않도록 `PreFlightContextGuard` 강제 적용.
- **Alternatives Considered**:
  - *정적 상수 유지 (6,000토큰)*: 게이트웨이의 16K/32K 대용량 윈도우 고도화 혜택을 100% 사장시킴.

---

### D3. Self-RAG Quality Gate & Hybrid Query Reformulation
- **Decision**: `QualityGradeNode`에서 1차 검색/리랭킹 결과(상위 점수 < 0.35 또는 0건)를 평가하고, 미달 시 형태소 동의어 사전(`alias_dictionary`) 확장과 Fast LLM(`qwen3.5-2b`) 문맥 재작성을 병렬 실행하는 하이브리드 재검색 루프(최대 1회) 가동.
- **Rationale**:
  - 사전 기반 확장은 초고속(< 0.1s)으로 브랜드/제품 별칭을 해결하고, Fast LLM은 복합 문맥 의도를 포착하므로 두 결과를 합성(Union & De-duplicate)하여 리랭킹할 때 가장 풍부한 검색 풀 확보 가능.
  - 루프 제한(최대 1회)을 두어 무한 순환 및 Latency 폭증을 원천 차단.
- **Alternatives Considered**:
  - *LLM 단독 재작성*: 지연 시간 1.5초 추가 및 단순 오타/별칭 누락 위험.
  - *사전 단독 확장*: 자연어 문맥 질의("끈적임 없는 가성비 세럼")에 대한 의미적 재구성 불가.

---

### D4. Hierarchical Memory & Redis On-Demand Deep Recall
- **Decision**: 최근 5턴은 원문 유지, 6~30턴은 `[Turn N: Entity/Attribute]` 태그를 포함한 3문장 요약으로 기본 압축하되, 대명사/지시어("아까 그 크림") 질의 시 Redis L4 세션 스토어에서 해당 턴의 원본을 < 2ms 내에 역조회하여 `<recalled_context>`로 동적 주입.
- **Rationale**:
  - 평상시 프롬프트 토큰을 수천 개 절약하여 최신 검색 리뷰 예산을 극대화.
  - 사용자가 과거 세부 수치(가격/성분/인용리뷰)를 질문할 때 100% 무손실로 완벽한 회상 답변 제공.
- **Alternatives Considered**:
  - *대화 전체 무압축 주입*: 20턴 누적 시 프롬프트 10,000토큰을 대화 로그가 잠식하여 검색 리뷰 수용 불가.
  - *단순 슬라이딩 윈도우(5턴 이전 삭제)*: 6턴 이전 내용에 대한 사용자 질문 시 "기억나지 않는다"며 대화 맥락 단절 발생.

---

### D5. Living Agent Inspector (동적 DAG 프로세스 시각화)
- **Decision**: 프론트엔드의 `phases = [...]` 정적 배열을 완전 제거하고, 백엔드 StateGraph의 `node_start` / `branch_fork` SSE 이벤트에 따라 타임라인에 실시간으로 서브 노드(`↳ 🔄 2차 재검색`, `↳ 🧠 Redis 역조회`)를 동적으로 추가 렌더링.
- **Rationale**:
  - 2026 글로벌 Agentic UI 표준(Perplexity Pro / Manus / OpenAI Canvas)과 일치.
  - 기술실증용 저사양 GPU(GTX 1070) 환경에서 사용자에게 실시간 서브스텝 피드백(진행률/소요시간/하트비트)을 제공하여 '화면 멈춤' 불안감을 완벽히 해소.
- **Alternatives Considered**:
  - *고정 4단계 유지*: 재검색이나 세션 역조회 분기 시 UI가 이전 단계에 머물러 시스템이 멈춘 것처럼 보임.

---

### D6. PILOS (A-Team) 대용량 일괄 리포트 하네스
- **Decision**: `ateam/pilos`의 `llm_report_client.py`에 `PilosExecutionHarness`를 도입하여, 일일 시장 뉴스 및 감성 데이터를 기존 10건에서 30~60건 이상 단일 프롬프트에 일괄 주입.
- **Rationale**:
  - 단일 컨텍스트 안에서 거시적 시장 흐름과 개별 종목 뉴스를 한 번에 상호 비교 분석 가능.
  - 여러 번 분할 호출하는 오버헤드 제거 및 종합 시장 감성 지수의 일관성 확보.
