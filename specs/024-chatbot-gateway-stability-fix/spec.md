# Feature Specification: 챗봇 A/B 런타임 오류 해결 및 vLLM 서빙 게이트웨이 OOM 방어·안정화

**Feature Name**: `024-chatbot-gateway-stability-fix`
**Created**: 2026-08-20
**Status**: Draft
**Priority**: P1 (Critical Reliability Fix)

---

## Clarifications

### Session 2026-08-20
- Q: Pilos 파이프라인(리포트 대량 생성)과 챗봇 A/B의 동시 요청 시 서빙 게이트웨이 OOM(Out of Memory)을 방어하기 위한 동시성 및 자원 제어 정책을 어떻게 설정할까요? → A: Option A (서브프로세스 즉각 자동 복구(Auto-Healing) + 챗봇 자동 재시도 + 동시 요청 세마포어 가드레일)

---

## Overview & Background

Pilos 파이프라인 가동 및 대량 백필/추론 수행 도중, B팀 챗봇 A와 챗봇 B에서 다음과 같은 치명적인 장애가 연쇄적으로 발생하였다.
1. **챗봇 B (`/bteam/chatb/`)**: `budget_context_documents()` 내에서 `is_9b` 변수 미정의로 인한 `NameError: name 'is_9b' is not defined` 통신 오류 발생
2. **챗봇 A (`/bteam/chata/`)**: `budget_context_documents()` 내 `is_9b` 변수 미정의 잠재 결함 및 LLM 게이트웨이 OOM 서브프로세스 다운으로 인한 `HTTP Error 503: Service Unavailable` 발생
3. **vLLM 서빙 게이트웨이 (`vllm-serv-gateway`)**: Pilos 리포트 대량 생성 및 챗봇 동시 요청 시 서브프로세스(Port 8089)가 `Linux Kernel OOM Killer (Exit Code: -9 / 137)`에 의해 종료된 후 자동 재시작/복구가 지연되는 안정성 결함

본 기능은 챗봇 A/B의 코드 수준 변수 참조 오류를 원천 제거하고, vLLM 서빙 게이트웨이의 OOM 방어, 프로세스 자동 복구(Auto-Restart Self-Healing) 및 동시성 제어를 강화하여 어떤 환경에서도 503 오류 없는 24/7 무중단 챗봇 서비스를 보장한다.

---

## User Stories

### User Story 1: 챗봇 B 정상 응답 및 변수 참조 무결성 확보 (Priority: P1) 🎯 MVP
- **As a** 챗봇 B를 사용하는 올리뷰 사용자
- **I want** 복합적인 뷰티/스킨케어 고민을 질의했을 때
- **So that** `name 'is_9b' is not defined`와 같은 통신 오류 없이 100% 매끄럽게 AI 전문 뷰티 가이드 맞춤 솔루션을 수신할 수 있다.

#### Acceptance Criteria
- **Scenario 1.1**: 챗봇 B에서 9B 또는 4B 모델을 대상으로 긴 문장의 리뷰 문서들을 주입할 때 `budget_context_documents()`가 `is_9b` 변수를 안전하게 판별하여 오류 없이 컨텍스트를 트리밍한다.
- **Scenario 1.2**: 챗봇 B의 추천 솔루션 및 스트리밍 응답이 0개의 Python 예외 없이 완벽하게 렌더링된다.

---

### User Story 2: 챗봇 A 코드 무결성 및 LLM 통신 안정성 확보 (Priority: P1)
- **As a** 챗봇 A를 사용하는 사용자
- **I want** 인기 앰플 추천 등 다양한 카테고리 질의를 요청했을 때
- **So that** 503 Service Unavailable이나 코드 예외 없이 2초 이내의 고속 추천 답변을 정상 수신한다.

#### Acceptance Criteria
- **Scenario 2.1**: `bteam/Oliview_chatbot_a/llm_common.py`의 `budget_context_documents()`에서 `is_9b` 변수 정의가 완비되어 단일/복수 문서 처리 시 예외가 발생하지 않는다.
- **Scenario 2.2**: LLM 게이트웨이 정상 연결 상태에서 모든 뷰티 질문이 200 OK로 스트리밍 생성된다.

---

### User Story 3: vLLM 서빙 게이트웨이 OOM 자가 치유(Self-Healing) 및 서브프로세스 복원 (Priority: P1)
- **As a** AISERVICE 플랫폼 운영자
- **I want** 백그라운드 Pilos 리포트 생성이나 피크 트래픽으로 서브프로세스가 일시 종료(OOM)되더라도
- **So that** 게이트웨이 매니저가 즉시 서브프로세스를 헬스체크하고 수 초 내에 자동 재기동(Auto-Restart)하여 챗봇 사용자가 503 장애를 겪지 않도록 한다.

#### Acceptance Criteria
- **Scenario 3.1**: 게이트웨이의 `ProcessManager`가 비정상 종료된 포트(8089)를 즉시 감지하여 안전하게 재생성한다.
- **Scenario 3.2**: VRAM/RAM 압박 상황에서도 프롬프트 캐시 상태 저장 시 OOM이 발생하지 않도록 메모리 세이프티 가드가 작동한다.

---

## Requirements

### Functional Requirements
- **FR-001**: `bteam/Oliview_chatbot_a/llm_common.py` 및 `bteam/Oliview_chatbot_b/common.py` 내 `budget_context_documents()` 함수에서 `is_9b = "9b" in str(model_name).lower()`를 명시적으로 선언하여 `NameError`를 원천 제거해야 한다.
- **FR-002**: 챗봇 A 및 챗봇 B의 모든 문서 트리밍 및 프롬프트 빌더 함수가 `model_name` 입력 유무에 관계없이 안전하게 fallback 처리되어야 한다.
- **FR-003**: `model_gateway`의 `ProcessManager`는 서브프로세스 헬스체크 실패 또는 종료 시 지체 없이 백그라운드 프로세스를 자동 재기동하여 503 응답을 방지해야 한다.
- **FR-004**: 챗봇 클라이언트는 LLM 호출 시 일시적인 503/502/연결 오류 발생 시 최대 2회 지수 백오프 자동 재시도를 수행하여 일시적 서브프로세스 재기동 중에도 사용자에게 에러를 노출하지 않아야 한다.
- **FR-005**: 챗봇 A, 챗봇 B 및 서빙 게이트웨이 도커 컨테이너가 최신 코드로 완벽 동기화 및 재빌드되어야 한다.

---

## Success Criteria

- **SC-001**: 챗봇 B 및 챗봇 A에서 10회 연속 질문 시 `NameError` 발생률 **0.0%**.
- **SC-002**: 챗봇 A 및 챗봇 B에서 `HTTP Error 503` 발생률 **0.0%**.
- **SC-003**: 서브프로세스 강제 종료 시 게이트웨이 자동 복원 시간 **< 5초**.
- **SC-004**: 챗봇 A/B E2E 회귀 테스트 100% 통과.
