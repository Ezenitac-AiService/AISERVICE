# Tasks: 올원챗 푸터 클린업 및 프롬프트 고도화·한자 차단 가드레일 (005-chatb-footer-cleanup)

**Feature**: `005-chatb-footer-cleanup`  
**Spec**: [spec.md](file:///c:/AISERVICE/specs/005-chatb-footer-cleanup/spec.md) | **Plan**: [plan.md](file:///c:/AISERVICE/specs/005-chatb-footer-cleanup/plan.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 대상 소스 파일 구조 점검 및 한자 차단 가드레일 기반 준비

- [X] T001 `bteam/Oliview_chatbot_b/index.html` 하단 416~417행 및 `project_ragapi.py` 프롬프트 구조 점검 in `bteam/Oliview_chatbot_b/index.html`, `bteam/Oliview_chatbot_b/project_ragapi.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 한자어 자동 치환 및 CJK 유니코드 정제 공통 모듈 구현

- [X] T002 한자어 사전 치환 및 CJK 유니코드 정제 함수(`clean_hanja_and_artifacts`) 구현 in `bteam/Oliview_chatbot_b/common.py`
- [X] T003 [P] 올리챗(ChatA) 연동을 위해 `clean_hanja_and_artifacts`를 `llm_common.py`에 동기화 in `bteam/Oliview_chatbot_a/llm_common.py`

**Checkpoint**: 한자 정제 후처리 가드레일 엔진 준비 완료

---

## Phase 3: User Story 1 - 올원챗 하단 불필요 텍스트 제거 및 프로덕션 푸터 정제 (Priority: P1) 🎯 MVP

**Goal**: `index.html` 문서의 `</html>` 바깥에 위치한 잔여 텍스트 라인을 완전히 삭제하여 프로덕션 푸터 완성

**Independent Test**: 브라우저에서 `https://ezenitac.duckdns.org/bteam/chatb/` 접속 후 최하단 스크롤 시 잔여 텍스트(`# http://localhost:8000/...`)가 0%로 완벽 제거되었는지 확인

### Implementation for User Story 1

- [X] T004 [US1] `bteam/Oliview_chatbot_b/index.html` 문서 최하단 416~417행(`# http://localhost:8000/...`) 영구 삭제 및 HTML5 닫는 태그 정리 in `bteam/Oliview_chatbot_b/index.html`

**Checkpoint**: User Story 1 (푸터 클린업) 완료

---

## Phase 4: User Story 2 - AI 뷰티 가이드 프롬프트 고도화 및 한자(漢字) 원천 차단 (Priority: P1)

**Goal**: RAG 프롬프트에 전문 뷰티 가이드 페르소나 및 순수 한글 지침을 주입하고, 후처리 파이프라인에서 한자를 100% 차단/치환

**Independent Test**: "차앤박 프로폴리스 앰플 수분감을 분석해줘" 질의 시 LLM 답변 본문에 한자(例: `結果`) 없이 순수 한글(`결과`)로 렌더링되는지 확인

### Implementation for User Story 2

- [X] T005 [US2] `project_ragapi.py` 시스템/사용자 프롬프트에 전문 뷰티 가이드 페르소나 및 100% 순수 현대 한국어(한자 혼용 절대 금지) 지침 주입 in `bteam/Oliview_chatbot_b/project_ragapi.py`
- [X] T006 [US2] `project_ragapi.py`의 `generate_llm_rag_answer` 함수 내 `clean_hanja_and_artifacts` 후처리 파이프라인 연동 in `bteam/Oliview_chatbot_b/project_ragapi.py`
- [X] T007 [P] [US2] 올리챗(ChatA) `06.02.app.py` 생성 후처리 파이프라인에도 `clean_hanja_and_artifacts` 연동 in `bteam/Oliview_chatbot_a/06.02.app.py`

**Checkpoint**: User Story 2 (프롬프트 고도화 및 한자 차단) 완료

---

## Phase 5: Polish & 종합 E2E 검증 (Cross-Cutting Concerns)

**Purpose**: 컨테이너 핫 리로드, 자연어 질의 검증 및 전체 E2E 10/10 PASS 유지 확인

- [X] T008 [P] `oliview_chatbot_b` 및 `oliview_chatbot_a` 컨테이너 재기동/핫 리로드 in `docker-compose.yml`
- [X] T009 "차앤박 프로폴리스 앰플 수분감을 분석해줘" 질의 테스트로 0% 한자 및 자연스러운 뷰티 가이드 답변 생성 검증 in `bteam/Oliview_chatbot_b/project_ragapi.py`
- [X] T010 `verify_e2e_services.ps1`을 실행하여 10대 체크포인트 100% PASS 유지 확인 in `specs/003-e2e-service-stabilization/scripts/verify_e2e_services.ps1`

---

## Dependencies & Execution Order

```mermaid
graph TD
    Phase1[Phase 1: Setup<br>T001] --> Phase2[Phase 2: Foundational<br>T002-T003]
    Phase2 --> US1[Phase 3: User Story 1 (P1)<br>Footer Cleanup<br>T004]
    Phase2 --> US2[Phase 4: User Story 2 (P1)<br>Prompt & Hanja Guardrail<br>T005-T007]
    US1 --> Phase5[Phase 5: Polish & E2E<br>T008-T010]
    US2 --> Phase5
```

---

## Implementation Strategy

### MVP Scope (User Story 1 + User Story 2)
1. `index.html` 최하단 잔여 텍스트 삭제 (T004)
2. `common.py` 한자 정제 헬퍼 함수 구현 (T002)
3. `project_ragapi.py` 프롬프트 고도화 및 후처리 연동 (T005, T006)
4. 컨테이너 재기동 및 자연어 질의/E2E 10/10 PASS 검증 (T008~T010)
