# Feature Specification: 035-service-context-window-expansion

**Feature Title**: Agentic AI Architecture, Harness Engineering, Living Process Inspector & Dynamic Context Window (16K/32K+) Expansion  
**Feature Branch**: `035-service-context-window-expansion`  
**Created**: 2026-08-26  
**Status**: Draft (Clarified with Living Agent Process Inspector & Dynamic DAG Visualization)  
**Input**: User description: "모델 게이트웨이 컨테이너 고도화로 확보된 16K/32K+ 대용량 컨텍스트 윈도우를 활용하여, 각 서비스(ateam/pilos, bteam/oliview, chatA, chatB)의 LLM 활용 구조를 진정한 Agentic AI 및 하네스 엔지니어링(Harness Engineering) 아키텍처로 전면 개편하고, 절차형 파이프라인을 진정한 LangGraph Compiled StateGraph로 승격하며, 고정된 4단계 진행상태 출력을 탈피하여 동적 분기/재검색 과정을 실시간 시각화하는 Living Process Inspector를 도입하는 리팩토링 스펙"

---

## Clarifications

### Session 2026-08-26
- **Q1**: LangGraph `Compiled StateGraph`로 전면 개편할 때, 1차 검색 결과 품질 미흡 시 동작하는 Self-RAG 재검색(Query Reformulation)의 트리거 기준과 재작성 방식을 어떻게 규정할까요? (FR-005)  
  → **A**: **A(사전 기반 동의어 확장)와 B(Fast LLM 문맥 재작성)의 하이브리드 비교 방식**을 적용한다. 본 플랫폼은 기술실증용(PoC)이므로 GTX 1070 등 저사양 GPU에서의 지연 시간은 실시간 UI 서브스텝 피드백(진행 상태, 하트비트, '멈춘 것이 아님' 시각화)과 넉넉한 슬라이딩 타임아웃으로 보장하며, 향후 상위 하드웨어 배포 및 실서비스 운용 모드 전환 시에는 엄격한 지연시간 방어선(Fast Path)이 동적으로 적용되도록 설계한다.

- **Q2**: 16K/32K+ 대용량 모드에서 15~30턴의 장기 대화 히스토리를 유지할 때, 과거 이전 턴의 메모리 하네스(Memory Harness) 압축 및 복원 정책을 어떻게 규정할까요? (FR-006)  
  → **A**: **계층형 슬라이딩 윈도우(최근 5턴 원문 + 6~30턴 핵심 요약)를 기본 적용하되, 사용자가 과거 압축된 대화의 세부 데이터(가격/성분/인용리뷰 등)를 요구하는 역참조 질의 시 Redis L4 세션 캐시에서 해당 턴의 원본을 온디맨드로 역조회(On-Demand Deep Recall)하여 동적 주입하는 하이브리드 메모리 아키텍처**를 적용한다.

- **Q3**: 사용자가 턴 번호(예: '10번째 대화')를 명시하지 않고 대명사나 지시어(예: '아까 말한 그 크림', '처음에 비교했던 거')를 사용할 때 비명시적 역참조를 어떻게 감지하고 복원할까요? (FR-006)  
  → **A**: **3단계 암묵적 지시어 해결 파이프라인(Anaphora Resolution Pipeline)**을 적용한다:  
  1. `session_summary`에 보존된 `[Turn N: 제품명/속성]` 메타데이터 태그와 사용자 질의의 지시어/속성을 우선 매칭한다.  
  2. 매칭이 모호할 경우, Redis L4에 저장된 과거 1~30턴 대화 텍스트를 대상으로 **초고속 세션 내 의미 유사도 검색(Session In-Memory Match, < 3ms)**을 실행하여 대상 턴을 자동 특정한다.  
  3. 특정된 턴의 원본 데이터(스펙 및 당시 인용 리뷰)를 `<recalled_context turn="N">` 태그로 현재 프롬프트에 동적 주입한다.

- **Q4**: ChatA와 ChatB의 정적 4단계 진행상태 출력을 탈피하여, 고도화된 동적 분기(품질 검증, 하이브리드 재검색, 세션 역조회 등)를 사용자에게 어떻게 시각화할까요? (FR-011)  
  → **A**: **2026 최신 트렌드 기반 'Living Agent Inspector' (동적 DAG 프로세스 뷰)**를 도입한다. 프론트엔드의 고정 단계 배열을 전면 폐지하고, LangGraph의 `node_start` / `branch_fork` SSE 이벤트에 따라 타임라인에 실시간으로 서브 노드(`↳ 🔄 2차 재검색`, `↳ 🧠 Redis 역조회`)를 동적 삽입하며, 마이크로 텔레메트리 뱃지(소요시간, 수집 건수, 16K 토큰량)를 표시하고 첫 토큰 수신 시 부드럽게 상단 요약 바로 축소(Auto-Collapse)한다.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Oliview Core (ChatA & ChatB) Compiled StateGraph & Living Process Inspector (Priority: P1) 🎯 MVP

사용자가 화장품 다중 제품 비교나 특정 제품의 심층 장단점을 질문할 때, 챗봇 서비스(`bteam/oliview_core`, `ChatA`, `ChatB`)가 **진정한 LangGraph Compiled StateGraph** 및 **Living Agent Inspector** 기반으로 작동하여, 1차 검색, 품질 검증, 하이브리드 재검색 분기, 세션 역조회 과정이 실시간 동적 트리로 시각화되며, 16K/32K+ 대용량 컨텍스트 하네스를 통해 고품질의 풍부한 비교 분석 답변을 스트리밍한다.

**Why this priority**:
절차형 스크립트와 정적 4단계 UI 틀을 완전 폐지하고, 실제 실행되는 LangGraph의 동적 분기 흐름을 투명하게 시각화함으로써 저사양 실증 환경에서도 사용자 신뢰도와 체감 만족도를 극대화합니다.

**Independent Test**:
복합 비교 질의 실행 시, 고정 4단계가 아닌 실제 실행된 노드(예: 1차 검색 ➔ 품질 검증 ➔ 하이브리드 재검색 분기 ➔ 컨텍스트 하네스 ➔ 답변 생성)가 UI에 실시간 추가되고, 마이크로 뱃지(소요시간, 건수)가 표시되는지 확인하여 독립 검증합니다.

**Acceptance Scenarios**:

1. **Given** 1차 검색 품질이 충분한 일반 비교 질의일 때,  
   **When** StateGraph가 실행되면,  
   **Then** UI Inspector에 기본 4개 노드가 순차 완료 처리되고 실시간 답변이 스트리밍된다.

2. **Given** 1차 검색 품질 미달로 하이브리드 재검색 또는 세션 역조회가 분기될 때,  
   **When** StateGraph가 조건부 엣지를 타면,  
   **Then** UI Inspector에 `↳ 🔄 하이브리드 재검색 중... (+0.5s)` 서브 브랜치 노드가 실시간 동적으로 추가 렌더링되어 사용자가 시스템의 자율적 문제 해결 과정을 실시간으로 확인할 수 있다.

---

### User Story 2 - Active Agentic Reflection & Retrieval Quality Gate (Priority: P2)

단순 일방향 검색-생성 파이프라인을 탈피하여, LangGraph 그래프 내에 **Retrieval Quality Grade Node(검색 품질 검증 노드)**를 도입함으로써, 1차 검색/리랭킹 결과가 사용자 질의를 충족하기에 부족하거나 편향된 경우, 에이전트가 스스로 판단하여 **하이브리드 재검색(동의어 확장 + Fast LLM 문맥 재작성 비교)**을 수행하고 보량 검색을 수행하는 능동적 피드백 루프를 가동한다.

**Why this priority**:
컨텍스트 윈도우가 16K/32K로 넓어졌더라도 쓰레기 데이터(Garbage-in)가 유입되면 환각(Hallucination)이 발생합니다. 에이전트가 자체적으로 검색 품질을 검증하고 하이브리드 방식으로 보완하는 능동적 루프가 필수적입니다.

**Independent Test**:
모호하거나 복합적인 질의(예: "민감성 피부인데 끈적임 없고 가성비 좋은 세럼 찾아줘")를 주입했을 때, 1차 검색 결과가 부실할 경우 StateGraph가 조건부 엣지(Conditional Edge)를 통해 재검색 노드로 분기하여 하이브리드 재작성 쿼리로 추가 컨텍스트를 확보한 후 최종 답변을 생성하는지 검증합니다.

**Acceptance Scenarios**:

1. **Given** 사용자의 복합 질의에 대해 1차 검색 결과의 관련성 점수가 기준치 미만일 때,  
   **When** `Quality Grade Node`가 상태를 평가하면,  
   **Then** `StateGraph`의 조건부 엣지가 작동하여 사전 기반 동의어 확장과 Fast LLM 문맥 재작성을 하이브리드로 비교·통합한 2차 검색을 자동 실행한 후 풍부한 컨텍스트를 조립한다.

2. **Given** 저사양 실증 환경(GTX 1070)에서 재검색 루프가 동작할 때,  
   **When** 추가 지연 시간이 발생하면,  
   **Then** UI 서브스텝 이벤트(진행 메시지, 하트비트, '비교 재검색 중')를 실시간 전송하여 사용자에게 정상 처리 중임을 피드백한다.

---

### User Story 3 - PILOS (A-Team) 대용량 일괄 리포트 하네스 및 다문서 분석 (Priority: P2)

시장 트렌드 및 감성 분석 서비스(`ateam/pilos`)가 모델 게이트웨이의 16K/32K+ 대용량 컨텍스트 윈도우를 활용하여, 일일/주간 감성 리포트 생성 시 기존 10건 내외에 머물던 뉴스 기사 및 커뮤니티 반응 데이터를 30건~60건 이상 단일 프롬프트에 일괄 주입하는 **Execution Harness**를 통해 결손 없는 종합 시장 감성 지표와 리포트를 도출한다.

**Why this priority**:
다수의 시장 뉴스를 분할 호출하거나 누락하지 않고 단일 컨텍스트에 통째로 수용함으로써 시장 전반의 정밀한 거시/미시 감성 트렌드를 한 번에 분석할 수 있습니다.

**Independent Test**:
일일 뉴스 50건에 대한 감성 분석 작업을 실행하여, Truncation 에러 없이 단일 프롬프트에서 종합 리포트가 정상 생성되는지 검증합니다.

**Acceptance Scenarios**:

1. **Given** 16K 이상의 컨텍스트가 활성화되어 있을 때,  
   **When** PILOS 리포트 수집기가 30건 이상의 일일 뉴스를 전달하면,  
   **Then** `PilosExecutionHarness`가 프롬프트 토큰을 검증하고 30건 전체를 단일 요청으로 처리하여 일관된 감성 점수와 분석 요약을 산출한다.

---

### User Story 4 - Evaluation & Observability Harness (Priority: P3)

16K/32K+ 대용량 컨텍스트 환경에서 에이전트의 응답 충실도(Faithfulness), 컨텍스트 활용 효율, 환각률, 지연 시간(TTFT)을 정량적으로 계측하고 회귀 결함을 사전에 감지하는 **Evaluation Harness**를 구축한다.

**Why this priority**:
대용량 프롬프트 주입 시 발생할 수 있는 "Lost in the Middle" 현상이나 환각을 지속적으로 모니터링하고 방어하기 위한 필수 검증 인프라입니다.

**Independent Test**:
표준 화장품 질의 10건 및 금융 뉴스 질의 10건으로 구성된 평가 벤치마크를 실행하여 정량 메트릭(인용 정확도, TTFT, 토큰 활용률)을 자동 출력합니다.

**Acceptance Scenarios**:

1. **Given** 벤치마크 평가 하네스를 가동할 때,  
   **When** 16K 및 32K 모드에서 테스트 질의를 수행하면,  
   **Then** 응답의 근거 인용 충실도(95% 이상)와 TTFT 지연시간 지표가 리포트로 출력된다.

---

## Edge Cases

- **게이트웨이 디스커버리 실패 또는 타임아웃**: 게이트웨이 엔드포인트 응답이 없을 경우, 안전한 기본값인 16K Baseline(입력 10,000토큰 예산)으로 즉시 폴백하여 클라이언트 중단을 방지한다.
- **다중 검색 루프 무한 순환 방지 (Infinite Loop Guard)**: Self-RAG 재검색 루프는 최대 1회로 제한하며, 1회 재검색 후에도 점수가 미달할 경우 확보된 최선의 컨텍스트와 함께 명시적 주의 문구(Disclaimer)를 첨부하여 답변을 완성한다.
- **대용량 프롬프트 초과 시 선별적 축소 정책**: 조립된 프롬프트가 안전 마진(유효 컨텍스트의 85%)을 초과할 경우, (1) 오래된 대화 히스토리 요약 -> (2) 최하위 랭킹 리뷰 제외 -> (3) 제품 스펙 축약 순으로 단계적 감축을 적용한다.
- **PoC vs Production 런타임 모드 전환**: PoC 모드에서는 충분한 타임아웃과 실시간 UI 서브스텝 피드백을 우선시하며, Production 모드에서는 엄격한 지연시간 SLA(Fast Path)를 적용하도록 환경변수(`RAG_OPERATION_MODE=poc|production`)로 제어한다.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `bteam/oliview_core`의 `graph_orchestrator.py`는 기존의 절차형 함수 호출을 제거하고, `langgraph.graph.StateGraph` 기반의 컴파일된 그래프(`compile()`) 객체로 전면 재작성되어야 한다.
- **FR-002**: `bteam/oliview_core`는 게이트웨이의 `GET /v1/models` 및 `GET /v1/profile`을 실시간 감지하여 `16K (Baseline)`, `32K (Standard)`, `64K+ (Ultra)` 3단계 예산 정책을 산정하는 `ContextHarness`를 구현해야 한다.
- **FR-003**: `bteam/oliview_core`의 `rerank_node`는 정적 3개 선별 제한을 제거하고, 16K 모드에서 타겟당 5~8개, 32K 모드에서 타겟당 10~15개의 리뷰를 동적 선별해야 한다.
- **FR-004**: `bteam/oliview_core`의 `context_node`는 16K 환경에서 최대 10,000토큰, 32K 환경에서 최대 22,000토큰의 고밀도 XML 샌드박스 컨텍스트를 조립해야 한다.
- **FR-005**: `bteam/oliview_core`의 `StateGraph`에 `QualityGradeNode`를 추가하여 검색 관련성이 미흡할 경우 사전 기반 동의어 확장과 Fast LLM 문맥 재작성을 하이브리드로 비교·통합하는 최대 1회의 Query Reformulation 재검색 루프를 수행해야 한다.
- **FR-006**: `bteam/oliview_core`의 `session.py` 및 `anaphora_resolver.py`는 `[Turn N: 제품명/속성]` 태그 기반 엔티티 매칭 및 세션 내 의미 검색을 통해 비명시적 대명사 질의 시 Redis L4에서 과거 턴 원본을 즉시 복원 주입하는 `AnaphoraDeepRecall` 하네스를 구축해야 한다.
- **FR-007**: `ateam/pilos`의 `llm_report_client.py`는 16K/32K 컨텍스트를 활용하여 단일 프롬프트에 30~60건 이상의 일일 뉴스/커뮤니티 데이터를 일괄 수용하는 `PilosExecutionHarness`를 도입해야 한다.
- **FR-008**: 모든 클라이언트는 프롬프트 전송 전 유효 컨텍스트의 85%를 초과하지 않도록 하는 `PreFlightContextGuard`를 내장해야 한다.
- **FR-009**: 에이전트의 응답 품질, 인용 충실도, 컨텍스트 효율을 지속 측정하는 `EvaluationHarness` 벤치마크 스크립트를 제공해야 한다.
- **FR-010**: 시스템은 PoC(기술실증) 모드와 Production(실서비스) 모드를 동적으로 구분하여, PoC 모드에서는 상세 서브스텝 UI 피드백과 넉넉한 슬라이딩 타임아웃을, Production 모드에서는 고속 지연시간 방어선을 적용해야 한다.
- **FR-011**: ChatA 및 ChatB 프론트엔드는 정적 4단계 UI 배열을 제거하고, 백엔드 StateGraph의 노드 실행/분기 이벤트(`node_start`, `branch_fork`)를 실시간 수신하여 타임라인에 자식 노드(`↳ 🔄 재검색`, `↳ 🧠 Redis 역조회`)를 동적으로 추가·렌더링하는 `Living Agent Inspector`를 구현해야 한다.

---

### Key Entities

- **CompiledStateGraph**: `langgraph.graph.StateGraph`를 통해 선언되고 노드 간 조건부 라우팅 및 상태 전달이 보장되는 런타임 그래프 실행체.
- **ContextHarnessProfile**: 감지된 게이트웨이 컨텍스트 크기(`total_n_ctx`)에 따라 입력 예산, 타겟당 리뷰 수, 히스토리 턴 수, 생성 토큰 상한을 규정하는 동적 하네스 엔티티.
- **LivingInspectorEvent**: 노드 식별자, 부모 노드 ID, 분기 여부(`is_branch`), 소요시간(`elapsed_ms`), 상태 뱃지 텍스트를 담은 동적 UI 이벤트 모델.
- **AnaphoraTurnMap**: 세션 요약에 포함되어 대명사("그 크림", "아까 비교한 거") 매칭 시 과거 특정 턴을 가리키는 `[Turn N: Entity/Attribute]` 매핑 레코드.
- **DeepRecallTurnPayload**: 사용자의 과거 대화 역참조 요청 시 Redis L4에서 온디맨드로 조회하여 컨텍스트에 동적 주입되는 과거 특정 턴의 질의/응답/참조리뷰 원본 데이터.
- **HybridQueryReformulationResult**: 동의어 사전 기반 확장 쿼리와 Fast LLM 기반 문맥 쿼리의 검색 결과를 비교·병합한 결과 집합.
- **QualityGradeVerdict**: 1차 검색 결과의 관련성 점수와 보완 필요 여부(`PASSED`, `RETRY_SEARCH`, `FALLBACK`)를 판정하는 평가 결과 객체.
- **EvaluationBenchmarkReport**: 응답 충실도, 할루시네이션 방어율, TTFT 지연시간, 토큰 소비 효율 메트릭을 요약한 평가 산출물.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 절차형 호출 파이프라인을 100% `LangGraph Compiled StateGraph` 엔진으로 전환 완료한다.
- **SC-002**: 화장품 비교 답변 생성 시 인용되는 사용자 리뷰 건수가 기존 제품당 3건에서 **최소 5건(16K)** ~ **10건 이상(32K)**으로 대폭 증가한다.
- **SC-003**: 대명사/지시어 기반 암묵적 역참조 질의("아까 그 크림") 시 과거 대화 데이터 복원 및 답변 정확도 **95% 이상**을 달성한다.
- **SC-004**: PILOS 일일 리포트 생성 시 단일 요청당 수용 가능한 뉴스 기사 건수가 기존 10건에서 **최소 30건 이상**으로 3배 확장된다.
- **SC-005**: 16K/32K 확장 가동 상태에서 프롬프트 초과(400 Context Exceeded) 및 OOM 발생률이 **0.0%**로 유지된다.
- **SC-006**: StateGraph의 분기/루프 발생 시 UI `Living Inspector`에 실시간 서브 노드가 100% 누락 없이 동적 렌더링되며, 첫 토큰 수신 시 부드러운 Auto-Collapse 애니메이션이 작동한다.

---

## Assumptions

- 모델 게이트웨이는 Spec 034에 따라 최소 16K(`16384`) 컨텍스트를 안정적으로 보장하며 `GET /v1/profile`을 통해 유효 크기를 제공한다.
- BGE-M3 및 BGE-Reranker는 각각 독립 포트(8090, 8091)에서 5.0초 이내에 후보 풀 검색 및 리랭킹을 완결한다.
- LangGraph v0.2+ 라이브러리가 컨테이너 환경에 설치되어 있으며 비동기 스트리밍(`astream`)을 온전히 지원한다.
- Redis(L4 세션 저장소)는 3일(`redis_ttl_session: 259200`) 동안 턴별 원문과 메타데이터를 유지한다.
- ChatA 및 ChatB 웹 UI는 표준 웹 브라우저(Chrome/Safari/Edge)에서 DOM 조작 및 SSE 이벤트 파싱을 지원한다.
