# Feature Specification: 039-zero-search-global-hard-block-and-category-recommendation (전역 제로 서치 하드 블록 및 카테고리 추천 RAG 무결성 보장)

**Feature Branch**: `039-zero-search-global-hard-block-and-category-recommendation`  
**Created**: 2026-08-26  
**Status**: Ready for Planning  
**Constitution Version**: v1.1.1 Compliant  
**Input**: User description: "여전히 검색 0건에 답변을 만들고 있음: ChatA 및 ChatB 전역 파이프라인에서 검색/선별 0건 시 26~33초 동안 '사용자 A/B/C', 가짜 후기 창작 문제 해결, 헌법 v1.1.1(DEMO/PRODUCTION 동적 환경 분리 및 무하드코딩 원칙) 준수, 하이브리드 Entity-Aspect DBMS 연동 및 oliview_core 단일화"

---

## Clarifications

### Session 2026-08-26
- **Q1 (DBMS 동적 인덱스)**: DBMS의 실존 브랜드/제품명 데이터를 활용하여 정적 화이트리스트를 대체하고 제로 서치를 검증하는 방식을 어떤 아키텍처로 구현할까요?  
  → **A**: **Option A+ (리뷰 보유 유효 상품 DBMS 동적 인메모리 인덱싱)**: 정적 화이트리스트(6개 브랜드) 대신, DBMS(`products` INNER JOIN `reviews` WHERE count $\ge 1$)에서 **실제로 리뷰가 1건 이상 수집·적재된 실존 상품 및 브랜드만 인메모리 인덱스 풀(`DynamicCatalogIndex`)로 로드**함. 리뷰가 없거나 미수집된 상품/브랜드 질의는 의도 분석(Normalization) 단계에서 감지되어 LLM 호출 전 즉시 제로 서치 하드 블록으로 사전 차단됨.
- **Q2 (전역 서비스 적용)**: ChatA 뿐만 아니라 ChatB(`project_ragapi.py`)에서도 선별 0건 시 26.9초 동안 가짜 후기를 생성하는 결함의 적용 범위는 어디까지인가?  
  → **A**: **전역 서비스 통합 하드 블록 (Global All-Service Hard Block)**: ChatA(Streamlit `app.py`, FastAPI `main.py`, `pipeline.py`, `graph_orchestrator.py`)와 ChatB(`project_ragapi.py`, `oliview_core`) 전 영역에서 선별 리뷰가 0건(`selected_review_count == 0` 또는 `web_response_list == []`)일 때 어떠한 LLM 호출도 전면 차단하고 제로 서치 템플릿을 즉시 반환함.
- **Q3 (하이브리드 Entity-Aspect RAG)**: RAG 시스템에 DBMS의 속성별 집계 뷰(`product_aspect_summaries`) 및 리뷰 보유 실존 상품 뷰(`v_active_rag_catalog`)를 연동하여 카테고리 추천 및 제로 서치 검증을 수행하는 설계를 채택할까요?  
  → **A**: **Option A (2026 하이브리드 Entity-Aspect RAG 채택)**: DBMS의 리뷰 보유 유효 상품 뷰(`v_active_rag_catalog`)와 속성 요약 테이블(`product_aspect_summaries`)을 연동하여, 카테고리/피부타입 추천 시 실존 대표 상품을 정확히 발굴하고 0건 환각을 원천 차단함.
- **Q4 (다중 페르소나 심층 검증 보강안)**: 성능 아키텍트, AI 환각 감사관, DB 회의론자, QA, PM 페르소나의 공격적 비판 사항을 어떻게 반영할까요?  
  → **A**: **전원 일치 보완안 승인 및 반영**:
    1. **소수 표본 왜곡 방지 (Small Sample Bias Defense)**: `total_review_count >= 5` 하한선 및 복합 랭킹 스코어(`positive_ratio * 0.7 + log(review_count) * 0.3`) 적용.
    2. **엄격한 인용 앵커링 (Strict Citation-Anchor Guard)**: `[제품명 리뷰 N]` 인라인 태그가 없는 모든 서술형 인용구 및 가짜 사용자 서술을 사후 정제기에서 100% 탈락.
    3. **이탈 방지 추천 칩(Alternative Chips)**: 제로 서치 응답에 인기 카테고리 칩 및 가이드 1클릭 추천 질문 제공.
- **Q5 (oliview_core 3개 폴더 단일 마스터 소스화 및 모듈 정리)**: 분산된 `oliview_core` 폴더들과 루트 레거시 스크립트들을 어떻게 정비할까요?  
  → **A**: **단일 마스터 동기화 및 레거시 격리 확정**: 루트 `bteam/oliview_core`를 최신 마스터 버전으로 완전 갱신하고, `Chat_a`와 `Chat_b` 내부 코어 모듈을 100% 동기화하며, 각 루트의 실험용 과거 스크립트(`01_...`, `04.reranking.py`, `common.py` 등)를 `legacy_archive/`로 격리 정돈함.
- **Q6 (헌법 v1.1.1 준수: DEMO/PRODUCTION 동적 환경 분리)**: 시연/운영 모드 분리 및 지연시간 기준을 어떻게 제어할 것인가?  
  → **A**: **환경 변수 기반 동적 주입 (Zero Hardcoding)**: `APP_RUN_MODE` (`DEMO` vs `PRODUCTION`) 환경 변수를 통해 런타임에 동적으로 모드를 전환함. `DEMO` 모드에서는 레거시 장비 제약을 수용하여 제로 서치 $\le 3.0$초, 일반 RAG $\le 20.0$초를 적용하며, `PRODUCTION` 모드에서는 고성능 SLA를 적용함. 모든 모드에서 **100% 무환각 및 실존 인용 보장 원칙**은 절대 준수함.

---

## 1. Problem Statement & User Value

### 배경 및 관측된 결함 (Observed Failure Modes)
- **증상 1 (ChatA)**: `"건성 피부에 촉촉하고 들뜸 없는 쿠션 추천해줘"` 질의 시 32.7초 소모하며 '사용자 A' 가짜 후기 창작.
- **증상 2 (ChatB)**: `"속건조가 너무 심해서 하루 종일 촉촉하고 흡수 잘되는 보습 영양 앰플 찾고 있어"` 질의 시 타임라인에 `리뷰 종합 분석 완료 (26.9초, 0건 선별)`이 표시되면서 본문에 **'사용자 A', '사용자 B', '사용자 C' 가짜 인용구** 및 허구의 분석글을 대량 생성함.
- **근본 원인**:
  1. **ChatA & ChatB 전역 파이프라인의 제로 서치 가드 우회 누락**:
     - ChatA `pipeline.py`: `reference_reviews`가 0건이어도 빈 컨텍스트로 LLM 호출.
     - ChatB `project_ragapi.py`: 필터링 후 `web_response_list`가 0건이어도 `generate_llm_rag_answer_stream`을 호출하여 빈 목록을 전달함으로써 LLM이 가짜 사용자 A/B/C를 지어냄.
  2. **정적 화이트리스트 및 비정형 벡터 단독 검색 한계**:
     - DBMS의 풍부한 정형 속성 및 집계 뷰를 활용하지 못하고 비정형 벡터 검색에만 의존하여 카테고리/피부타입 추천 시 0건이 반환되거나 엉뚱한 제품 수집.
  3. **익명 플레이스홀더("사용자 A", "고객 B") 및 서술형 인용 가드레일 부재**:
     - 인라인 인용(`[제품명 리뷰 N]`)이 결속되지 않은 가짜 인용구 작성을 시스템 레벨에서 원천 금지하지 못함.
  4. **폴더 및 코어 모듈 분산에 따른 유지보수 혼선**:
     - `oliview_core` 패키지가 3곳에 파편화되어 있고 루트에 과거 스크립트가 방치되어 동기화 누락 발생.

---

## 2. User Scenarios & Testing *(mandatory)*

### User Story 1 - 2026 CRAG 기반 전역 제로 서치 즉시 하드 블록 (Priority: P1) 🎯 MVP

사용자가 올리브영 데이터베이스에 리뷰가 0건인 질문(비존재 제품, 미보유 카테고리, 리뷰 미수집 상품 등)을 입력했을 때, ChatA(Streamlit, FastAPI) 및 ChatB(`project_ragapi.py`) 어느 진입점에서도 LangGraph 조건부 에지(`should_abstain_zero_search`)에서 즉시 감지하여 LLM 호출 없이 **동적 설정된 SLA(DEMO 모드 시 3.0초 이내, PRODUCTION 모드 시 0.5초 이내) 내에 정직한 부재 고지 및 대체 추천 칩을 즉시 출력**한다.

**Why this priority**: 리뷰 0건 시 25~35초 동안 가짜 리뷰와 가짜 사용자(A/B/C)를 지어내는 현상은 서비스 신뢰도를 파괴하는 최우선 결함이며, 헌법 원칙 VI에 따라 100% 무환각(Zero-Hallucination)이 보장되어야 한다.

**Independent Test**:
- 질의: `"속건조 심해서 보습 영양 앰플 찾고 있어"` (선별 0건 상태) 또는 `"화성인 안드로메다 수분크림 추천해줘"`
- 검증: ChatA 및 ChatB 양쪽 모두에서 SLA 이내에 `ZERO_SEARCH_TEMPLATE` 즉시 반환, LLM 호출 차단, 및 추천 칩 정상 노출 확인.

**Acceptance Scenarios**:
1. **Given** RAG 파이프라인에서 선별된 유효 리뷰가 0건(`selected_review_count == 0` 또는 `web_response_list == []`)일 때,
   **When** ChatA 또는 ChatB를 통해 사용자가 질문하면,
   **Then** `synthesis_stream` 호출을 사전에 우회하고 동적 SLA 이내에 정형화된 제로 서치 안내 메시지와 카테고리 칩을 반환한다.
2. **Given** 제로 서치 상태가 발동되었을 때,
   **When** 응답 본문을 검증하면,
   **Then** '사용자 A', '사용자 B', '사용자 C', 서술형 가짜 인용구 등 어떠한 가짜 후기도 포함되지 않아야 한다.

---

### User Story 2 - 하이브리드 Entity-Aspect DBMS 연동 및 카테고리 추천 (Priority: P2)

정적 화이트리스트에 의존하지 않고 DBMS의 유효 리뷰 보유 상품 뷰(`v_active_rag_catalog`) 및 속성 요약 테이블(`product_aspect_summaries`)을 연동하여, 사용자가 `"건성 피부에 촉촉하고 들뜸 없는 쿠션 추천해줘"`, `"속건조 영양 앰플 추천해줘"` 등 열린 추천 질의 입력 시 리뷰가 풍부한 실존 인기 상품 2~3종을 자동 발굴하여 실제 리뷰 기반 비교 추천을 제공한다.

**Why this priority**: 실제 리뷰가 수집되어 검증 가능한 제품들만 RAG 타겟으로 선별하여야만, 미수집 상품으로 인한 빈 컨텍스트 및 가짜 추천을 원천 차단하고 높은 추천 품질을 보장할 수 있다.

**Independent Test**:
- 질의: `"건성 피부에 촉촉하고 들뜸 없는 쿠션 추천해줘"`
- 검증: DBMS의 리뷰 5건 이상 보유 실존 쿠션 2~3종(예: "헤라 블랙 쿠션", "롬앤 블룸 인 커버핏 쿠션" 등)이 발굴되고, 각 제품별 실제 리뷰와 `[제품명 리뷰 N]` 태그가 포함된 비교 요약이 출력됨.

**Acceptance Scenarios**:
1. **Given** DBMS에 수만 개의 상품이 등록되어 있으나 일부만 실제 리뷰가 수집되어 있을 때,
   **When** 동적 카탈로그 인덱스를 구축하면,
   **Then** `reviews` 테이블에 유효 리뷰가 1건 이상 존재하는 상품 및 브랜드(`v_active_rag_catalog`)만 유효 탐색 풀로 로드한다.
2. **Given** 사용자가 품목/피부타입 추천 질의를 입력했을 때,
   **When** 카테고리 탐색 엔진이 실행되면,
   **Then** `product_aspect_summaries`의 복합 스코어(`positive_ratio * 0.7 + log(review_count) * 0.3`) 및 최소 리뷰 수($\ge 5$) 조건을 기반으로 상위 대표 상품 2~3종을 타겟으로 자동 확장하여 `[제품명 리뷰 N]` 인용과 함께 답변을 생성한다.

---

### User Story 3 - 엄격한 인용 앵커링(Strict Citation-Anchor) 및 가짜 사용자 차단 (Priority: P3)

LLM이 답변을 생성하는 과정에서 인라인 인용(`[제품명 리뷰 N]`) 태그 없이 `"사용자 A"`, `"사용자 B"`, `"어떤 구매자는..."` 등 익명의 가짜 인용구를 창작하는 패턴을 탐지하여 사후 근거 일치성 정제기(`GroundednessSanitizer`)가 원천 차단하고 정제한다.

**Why this priority**: LLM의 본성상 근거 데이터가 부족할 때 흔히 주어를 우회하여 허구적 일반화를 시도하므로, 인용 태그가 물리적으로 결속되지 않은 모든 문장을 사후 정제기 수준에서 엄격하게 제거해야 한다.

**Independent Test**:
- LLM 출력에 `사용자 A`, `사용자 B`, `서술형 인용구` 등의 허구 패턴이 주입되었을 때, 후처리 가드레일에서 즉시 감지되어 정제되거나 제로 서치로 전환되는지 검증.

**Acceptance Scenarios**:
1. **Given** LLM 생성 프롬프트가 구성될 때,
   **When** 시스템 프롬프트를 주입하면,
   **Then** "임의의 사용자 가명 사용 절대 금지", "컨텍스트에 없는 문장 창작 금지", "모든 인용문 뒤에 `[제품명 리뷰 N]` 명시 필수" 지침이 강력하게 적용된다.
2. **Given** 생성된 결과물에 인라인 인용 태그가 결속되지 않은 허구 인용문이 포함된 경우,
   **When** `GroundednessSanitizer`가 실행되면,
   **Then** 해당 허구 문장을 완전히 제거하거나 교정한다.

---

### User Story 4 - ChatA 및 ChatB 전역 아키텍처 일원화 및 모듈 클린 재구성 (Priority: P4)

ChatA(Streamlit `app.py`, FastAPI `main.py`)와 ChatB(`project_ragapi.py`) 모두 단일 통합 `MultiTargetGraphOrchestrator`와 공통 가드레일을 공유하도록 정렬하고, 루트 `bteam/oliview_core`를 단일 마스터 소스로 100% 동기화하며, 프로젝트 루트의 과거 레거시 스크립트들을 `legacy_archive/`로 격리 정돈한다.

**Why this priority**: 헌법 원칙 III(서비스 모듈화)에 따라 전사적 일관성을 확보하고 클린 아키텍처를 유지해야 한다.

**Independent Test**:
- ChatA와 ChatB에서 동일한 제로 서치 및 추천 질의를 수행하여 동일한 가드레일 및 결과가 반환됨을 검증하고, `bteam/oliview_core`와 양 챗봇 내부 코어가 100% 일치함을 검증.

**Acceptance Scenarios**:
1. **Given** ChatA 및 ChatB의 API 또는 UI에서 요청이 인입될 때,
   **When** 파이프라인이 실행되면,
   **Then** 통일된 `DynamicCatalogIndex` 및 전역 Zero-Search Hard Block 규칙이 동일하게 적용된다.
2. **Given** 챗봇 프로젝트 디렉토리를 검증할 때,
   **When** 코어 모듈 및 루트를 검사하면,
   **Then** `bteam/oliview_core`, `Chat_a/oliview_core`, `Chat_b/oliview_core` 3곳이 완전히 동기화되어 있고 과거 스크립트는 `legacy_archive/`로 안전하게 격리되어 있다.

---

## 3. Edge Cases & Boundary Conditions

1. **카테고리는 인식되었으나 해당 카테고리에 등록된 리뷰가 0건인 경우**:
   - 즉시 User Story 1의 제로 서치 하드 블록 발동 (동적 SLA 이내 정직한 부재 안내 및 추천 칩 표시).
2. **DBMS 연결 일시 실패 시**:
   - ChromaDB/Vector 메타데이터 인덱스로 자동 안전 폴백하여 서비스 중단 방지.
3. **복합 피부 타입 질의 (예: "속건조가 심하고 유분도 많아")**:
   - 복합 피부타입 속성을 추출하여 수분/진정 앰플 카테고리 유효 리뷰 보유 상품 발굴.

---

## 4. Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 시스템은 ChatA(`pipeline.py`, `graph_orchestrator.py`, `app.py`, `main.py`) 및 ChatB(`project_ragapi.py`, `oliview_core`) 전 영역에서 선별 리뷰가 0건일 경우 LangGraph 조건부 에지(`should_abstain_zero_search`)에서 LLM 호출을 사전에 우회하고 설정된 SLA 이내에 `ZERO_SEARCH_TEMPLATE`과 추천 칩을 반환해야 한다.
- **FR-002**: 시스템은 정적 화이트리스트 대신 DBMS 유효 리뷰 보유 상품 뷰(`v_active_rag_catalog`) 및 속성 요약 테이블(`product_aspect_summaries`)을 연동하여 서버 기동 시 인메모리 `DynamicCatalogIndex`를 구축하고 실존 여부를 사전 검증해야 한다.
- **FR-003**: 품목/카테고리/피부타입 기반 열린 추천 질의(예: "속건조 보습 영양 앰플 추천", "건성 피부 쿠션 추천") 입력 시, `product_aspect_summaries`에서 최소 리뷰 수($\ge 5$) 및 복합 랭킹 스코어가 높은 실존 인기 상품 2~3종을 자동 선별하여 다중 타겟 RAG로 연계해야 한다.
- **FR-004**: 시스템은 사후 근거 일치성 정제기(`GroundednessSanitizer`)를 가드레일에 도입하여 `[제품명 리뷰 N]` 태그가 결속되지 않은 "사용자 A/B/C" 및 서술형 가짜 인용구를 100% 탐지·제거해야 한다.
- **FR-005**: Streamlit `app.py` 및 ChatB `project_ragapi.py`의 진입점을 `MultiTargetGraphOrchestrator` 기반으로 일원화하여 레거시 파이프라인 우회 경로를 제거해야 한다.
- **FR-006**: `bteam/oliview_core`, `Chat_a/oliview_core`, `Chat_b/oliview_core` 3개 폴더를 100% 동일하게 마스터 동기화하고, 각 루트의 과거 레거시 스크립트들을 `legacy_archive/`로 격리 정돈해야 한다.
- **FR-007 (헌법 원칙 VI 준수)**: 시스템은 `APP_RUN_MODE` 환경 변수(`.env`, `DEMO` vs `PRODUCTION`) 및 `Settings` 객체를 통해 런타임에 동적으로 운영 모드를 전환해야 하며, 어떠한 SLA 기준이나 모드 분기도 하드코딩되어서는 안 된다.

### Key Entities

- **ActiveCatalogView (`v_active_rag_catalog`)**: DBMS에서 유효 리뷰가 $\ge 1$건 이상 존재하는 실존 브랜드 및 상품 뷰.
- **ProductAspectSummary (`product_aspect_summaries`)**: 상품별 속성(수분감, 각질부각 등) 긍/부정 수 및 비율 사전 집계 엔티티.
- **DynamicCatalogIndex**: 서버 시작 시 DBMS에서 로드되는 인메모리 실존 카탈로그 인덱스 (Set/Trie 구조).
- **GroundednessSanitizer**: 생성된 마크다운 텍스트에서 비인증 익명 사용자 인용구를 제거하고 실존 인용 태그(`[제품명 리뷰 N]`)와의 정합성을 보장하는 사후 정제기.
- **AppRunMode**: `DEMO` 또는 `PRODUCTION`을 나타내는 런타임 환경 설정 열거형.

---

## 5. Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: ChatA 및 ChatB 전 영역에서 리뷰 0건 질의 시 응답 지연 시간 $\le 3.0$초 (DEMO 모드 기준) / $\le 0.5$초 (PRODUCTION 모드 기준) 달성 (LLM 호출을 사전에 생략하여 25~35초 대기 환각을 원천 차단).
- **SC-002**: 리뷰 0건 및 추천 질의 환경에서 '사용자 A', '사용자 B', '사용자 C', '서술형 가짜 후기' 발생률 **0.0%** (100% 무환각 달성).
- **SC-003**: 열린 추천 질의 시 DBMS 리뷰 보유 실존 상품 2~3종 발굴 및 `[제품명 리뷰 N]` 인용 부호 포함률 **100%**.
- **SC-004**: 단위/통합 테스트 전수 통과, `APP_RUN_MODE` 동적 전환 테스트 통과, 3개 `oliview_core` 패키지 100% 동기화 달성.

---

## 6. Constitution Alignment Matrix (헌법 v1.1.1 정합성 검증)

| 헌법 원칙 | 준수 전략 및 명세서 반영 내용 | 적합성 판정 |
|:---|:---|:---:|
| **I. 언어 정책 (Korean)** | 사용자 소통, 명세서, 주석, 부재 고지 템플릿 전원 한국어 작성 | 🟢 PASS |
| **II. TDD 우선주의** | 테스트 선행 작성(Zero-Search Gate, Groundedness Sanitizer, Dynamic Catalog Test) | 🟢 PASS |
| **III. 서비스 모듈화** | 3개 `oliview_core` 패키지 동기화 및 `legacy_archive/` 격리 | 🟢 PASS |
| **IV. 관측 가능성** | 제로 서치 발생 및 CRAG Fast-Path 이벤트 JSON 구조화 로깅 | 🟢 PASS |
| **V. 단순성 및 YAGNI** | 기존 MySQL 뷰 및 LangGraph 조건부 에지 활용 (불필요한 과도 추상화 방지) | 🟢 PASS |
| **VI. 환경별 이원화 & 동적 설정** | `APP_RUN_MODE=DEMO/PRODUCTION` 무하드코딩 및 런타임 동적 주입 | 🟢 PASS |

---

## 7. Assumptions

1. 올리브영 MySQL DBMS에 `products`, `reviews`, `review_aspect_sentences`, `aspect_sentiment_results` 테이블이 구성되어 있다.
2. 서버 시작 시 또는 백그라운드 스케줄러로 `DynamicCatalogIndex`를 빌드할 때 메모리 부하(수 MB 수준)는 극히 경미하다.
3. Python 3.12 환경 및 기존 BGE-Reranker, Faiss/BM25 검색 인프라를 온전하게 활용한다.
4. `APP_RUN_MODE` 환경 변수에 따라 시연(DEMO) 및 상용(PRODUCTION) 모드가 동적으로 분기된다.
