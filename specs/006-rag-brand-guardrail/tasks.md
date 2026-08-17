# Tasks: RAG 브랜드 엔티티 인식 및 데이터 결측치 배제·올리뷰 브랜드 조회 정규화 (006-rag-brand-guardrail)

**Feature**: `006-rag-brand-guardrail`  
**Spec**: [spec.md](file:///c:/AISERVICE/specs/006-rag-brand-guardrail/spec.md) | **Plan**: [plan.md](file:///c:/AISERVICE/specs/006-rag-brand-guardrail/plan.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 대상 프론트엔드 URL 접두사 및 백엔드 RAG 쿼리 파이프라인 구조 점검

- [X] T001 `bteam/Oliview_Project/frontend/src/App.jsx` API 베이스 URL 설정 및 `common.py` / `project_ragapi.py` 쿼리 파이프라인 점검 in `bteam/Oliview_Project/frontend/src/App.jsx`, `bteam/Oliview_chatbot_b/common.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 불용어 필터링, 활성 브랜드 사전 캐시 및 브랜드 엔티티 매처 공통 모듈 구현

- [X] T002 불용어 세트(`RAG_STOPWORDS`), 활성 브랜드 로더 및 브랜드 엔티티 추출 함수(`extract_brand_entity`) 구현 in `bteam/Oliview_chatbot_b/common.py`
- [X] T003 [P] 올리챗(ChatA) 연동을 위해 `RAG_STOPWORDS` 및 `extract_brand_entity`를 `llm_common.py`에 동기화 in `bteam/Oliview_chatbot_a/llm_common.py`

**Checkpoint**: 브랜드 엔티티 인식 및 불용어 정제 엔진 준비 완료

---

## Phase 3: User Story 3 - 올리뷰(Oliview) 로그인/회원가입 브랜드 고유번호 조회 404 버그 해결 (Priority: P1)

**Goal**: `App.jsx`의 `API_BASE_URL`을 `'/bteam/oliview'`로 변경하여 로그인/회원가입 모달의 Double `/api/` 404 오류 영구 해결

**Independent Test**: 브라우저에서 `https://ezenitac.duckdns.org/bteam/oliview/` 로그인 페이지의 [조회하기] 클릭 -> "헤라" 검색 시 `헤라 (ID: 68)`가 정상 반환되는지 확인

### Implementation for User Story 3

- [X] T004 [US3] `bteam/Oliview_Project/frontend/src/App.jsx`의 `API_BASE_URL` 기본값을 `'/bteam/oliview'`로 정규화 in `bteam/Oliview_Project/frontend/src/App.jsx`

**Checkpoint**: User Story 3 (올리뷰 프론트엔드 브랜드 조회 404 해결) 완료

---

## Phase 4: User Story 2 - RAG 검색 데이터 품질 정제 및 결측치(`NULL`/빈값/미분류) 원천 차단 (Priority: P1)

**Goal**: RAG 1단계 DB 쿼리에서 브랜드명 및 상품명이 비어있는 56.6%의 결측치 데이터를 원천 배제하여 `[익명]` 및 `미분류` 환각 차단

**Independent Test**: 일반 검색 질의("진정 세럼", "수분크림") 실행 시 모든 추천 결과의 `brand_name`과 `product_name`이 빈값이나 `미분류`가 아닌 실제 상품인지 확인

### Implementation for User Story 2

- [X] T005 [US2] `project_ragapi.py`의 1단계 DB 후보군 조회 SQL에 `brand_name` 및 `product_name` 유효성(`IS NOT NULL AND != '' AND != '미분류'`) 필수 조건 추가 in `bteam/Oliview_chatbot_b/project_ragapi.py`

**Checkpoint**: User Story 2 (결측치 데이터 배제) 완료

---

## Phase 5: User Story 1 - 미등록/부재 브랜드 질의 시 엉뚱한 추천 차단 및 정확한 안내 (Priority: P1) 🎯 MVP

**Goal**: 부재 브랜드(예: '헤라', '샤넬') 질의 시 무관한 타사 제품 추천 및 `[익명]` 브랜드 생성을 원천 차단하고 표준 부재 안내문 반환

**Independent Test**: "헤라 스킨케어 제품 추천해줘" 질의 시 `[익명]`이나 타사 제품 카드 없이 "죄송합니다. 현재 '헤라' 브랜드의 등록 상품 및 리뷰 데이터가 올리뷰에 존재하지 않습니다." 표준 안내문 반환 확인

### Implementation for User Story 1

- [X] T006 [US1] `project_ragapi.py`에 `extract_brand_entity` 연동 및 리뷰 0건 브랜드 질의 시 즉시 0-결과 표준 안내문 반환 로직 구현 in `bteam/Oliview_chatbot_b/project_ragapi.py`
- [X] T007 [US1] `project_ragapi.py` 시스템 프롬프트에 질문과 불일치하는 타사 제품을 지어내거나 `[익명]` 브랜드로 출력하는 것을 금지하는 네거티브 가드레일 추가 in `bteam/Oliview_chatbot_b/project_ragapi.py`

**Checkpoint**: User Story 1 (부재 브랜드 방어 가드레일) 완료

---

## Phase 6: User Story 4 - 불용어(Stopwords) 필터링 및 리랭킹 신뢰도 컷오프 (Priority: P2)

**Goal**: '스킨케어', '제품', '추천' 등 일반 불용어를 검색 토큰에서 제외하여 검색 오염을 방지하고 최소 신뢰도 미달 항목 배제

**Independent Test**: "asdfg 화장품 제품 추천해줘" 질의 시 무관한 제품 추천 없이 0-결과 폴백이 정상 동작하는지 확인

### Implementation for User Story 4

- [X] T008 [US4] `project_ragapi.py` 질의 토큰 추출 시 `RAG_STOPWORDS` 필터링 적용 및 최소 신뢰도 컷오프 임계값 적용 in `bteam/Oliview_chatbot_b/project_ragapi.py`

**Checkpoint**: User Story 4 (불용어 필터링 및 임계값 제어) 완료

---

## Phase 7: Polish & 종합 E2E 검증 (Cross-Cutting Concerns)

**Purpose**: 컨테이너 재기동, 실측 자연어 질의 검증 및 전체 E2E 10/10 PASS 유지 확인

- [X] T009 [P] `oliview_frontend`, `oliview_chatbot_b`, `oliview_chatbot_a` 컨테이너 재기동 in `docker-compose.yml`
- [X] T010 올리뷰 로그인 모달에서 "헤라" 브랜드 조회(`헤라 ID: 68`) 및 올원챗 "헤라 스킨케어", "차앤박 프로폴리스 앰플" 질의 실측 검증 in `specs/006-rag-brand-guardrail/quickstart.md`
- [X] T011 `verify_e2e_services.ps1`을 실행하여 10대 체크포인트 100% PASS 유지 확인 in `specs/003-e2e-service-stabilization/scripts/verify_e2e_services.ps1`

---

## Dependencies & Execution Order

```mermaid
graph TD
    Phase1[Phase 1: Setup<br>T001] --> Phase2[Phase 2: Foundational<br>T002-T003]
    Phase2 --> US3[Phase 3: User Story 3 (P1)<br>Oliview Brand Search 404 Fix<br>T004]
    Phase2 --> US2[Phase 4: User Story 2 (P1)<br>DB NULL/Empty Exclusion<br>T005]
    Phase2 --> US1[Phase 5: User Story 1 (P1)<br>Brand Entity & Negative Prompt<br>T006-T007]
    US1 --> US4[Phase 6: User Story 4 (P2)<br>Stopwords & Thresholds<br>T008]
    US3 --> Phase7[Phase 7: Polish & E2E<br>T009-T011]
    US2 --> Phase7
    US4 --> Phase7
```

---

## Implementation Strategy

### MVP Scope (User Story 3 + User Story 2 + User Story 1)
1. `App.jsx` API Base URL 정규화로 브랜드 검색 404 해결 (T004)
2. `common.py` 불용어 및 브랜드 엔티티 매처 구현 (T002)
3. `project_ragapi.py` SQL 결측치 배제 및 부재 브랜드 0-결과 폴백 적용 (T005, T006, T007)
4. 컨테이너 재기동 및 "헤라", "차앤박" 질의/E2E 10/10 PASS 검증 (T009~T011)
