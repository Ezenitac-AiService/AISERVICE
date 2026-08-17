# Feature Specification: PILOS 챗봇 LLM 응답 지연 해소 및 로컬 GPU 스트리밍·캐시 가속 (008-pilos-chatbot-latency-optimization)

**Feature Branch**: `008-pilos-chatbot-latency-optimization`

**Created**: 2026-08-18

**Status**: Specified

**Input**: User description: "로컬 llm 이기때문에 3초내 완결된 답변 제공은 무리임. 문제는 llm 호출을 계속 하고 있는데, 답변이 완성이 안되는것임. 뒤에서는 답변 만들 작업을 하고 있는데(gpu 작업중임) 프론트에서는 타임아웃이 남. 정본 캐시는 10초 이내에 / 동적 생성은 스트리밍으로 과정을 출력하는게 나을거 같음. 스트리밍으로 출력을 한다면, 추론 코드 같은 경우 추론이 다 된 경우 어떻게 처리할것인가? 이 작업을 하면서 다른 챗봇이 망가지면 안됨"

---

## Clarifications

### Session 2026-08-18
- **Q**: 서비스 지식 및 동적 LLM 답변 생성의 처리 방식 및 응답 인터페이스 기준?
- **A**: 정적 서비스 지식(15개 질문 블록)은 정본 캐시(Knowledge Cache)를 통해 10초 이내(통상 1~3초)에 안정적으로 반환하고, 동적 LLM 생성은 실시간 스트리밍(Streaming / SSE)으로 토큰 생성 과정을 화면에 점진 출력하여 체감 지연을 해소하고 프론트엔드/게이트웨이 타임아웃 오류를 원천 차단하기로 결정.
- **Q**: 로컬 LLM(GTX 1070) 환경에서 발생하는 조기 타임아웃 및 재시도 폭주 방지 방안?
- **A**: 백엔드 LLM 클라이언트의 조기 타임아웃(30초) 및 중복 3회 재시도 루프를 단일 스트림/장기 타임아웃(90~120초)으로 정상화하고, Nginx 프록시 버퍼링 해제(`proxy_buffering off;`)를 적용하여 GPU 연산과 클라이언트 수신을 실시간으로 동기화.
- **Q**: 스트리밍 답변 생성 완료 시점(추론 완료 후) 백엔드와 프론트엔드의 처리 프로토콜?
- **A**: LLM 토큰 생성이 완료되면 백엔드는 최종 완료 이벤트(`type: "done"`)와 함께 출처(Sources), 상태(Status), 경고(Warnings), 후속 추천 질문(Follow-ups) 메타데이터를 전송하고 스트림을 종료함. 프론트엔드는 스트림을 닫고 마크다운 최종 서식 확정, 근거 칩(Sources) 렌더링, 후속 질문 버튼 활성화 및 입력 제어를 복원함.
- **Q**: 타 서브시스템 챗봇(B-Team 올리챗 Streamlit, 올원챗 FastAPI)과의 격리 및 회귀 방지 정책?
- **A**: 본 작업의 모든 코드 수정 및 캐시 모듈은 A-Team Pilos(`ateam/pilos-sentiment-index/`) 내부에 엄격히 격리(Isolation)하며, Nginx 게이트웨이의 B-Team 라우팅(`/bteam/chata/`, `/bteam/chatb/`, `/bteam/oliview/`) 및 공용 환경변수 구조를 절대 훼손하지 않음. 또한 Pilos의 불필요한 GPU 호출 감소로 공유 GPU 자원을 확보하여 전체 챗봇의 안정성을 향상함.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 정본 서비스 지식 10초 이내 고속 반환 및 GPU 낭비 차단 (Priority: P1) 🎯 MVP

사용자가 챗봇에서 서비스 개요, 연구 대상, 두 방향 모델, 데이터 항목, 해석 유의사항 등 등록된 서비스 지식 질문 블록을 선택했을 때, 매번 로컬 GPU에서 무거운 RAG/LLM 연산을 반복하지 않고 사전에 검증된 정본 캐시(Knowledge Cache)를 통해 **10초 이내(통상 1~3초)**에 완결된 답변과 공식 출처를 즉시 확인해야 합니다.

**Why this priority**: 정적 서비스 소개 및 해석 기준은 불변 데이터이므로, 캐시 우선 처리를 통해 로컬 GPU(GTX 1070)의 불필요한 부하를 완전히 없애고 사용자에게 즉각적이고 신뢰할 수 있는 답변을 제공할 수 있습니다.

**Independent Test**:
- 챗봇 패널에서 "PILOS 연구 알아보기"의 15개 질문 블록(연구 대상, 두 방향 모델, 분석 결과 해석 등)을 순차 클릭했을 때, GPU 부하 없이 10초 이내에 완결된 정본 답변과 출처가 정상 출력되는지 검증.

**Acceptance Scenarios**:

1. **Given** 등록된 서비스 지식 질문 블록, **When** 사용자가 해당 블록을 선택하면, **Then** 10초 이내에 사전 검증된 정본 답변과 출처가 화면에 완벽히 렌더링된다.
2. **Given** 캐시된 서비스 지식 답변, **When** 화면에 출력될 때, **Then** 마크다운 서식(강조, 목록, 인용문)과 출처 라벨이 깨짐 없이 온전히 표시된다.

---

### User Story 2 - 동적 LLM 생성 시 실시간 스트리밍 및 완료 시 메타데이터 융합 (Priority: P1)

사용자가 동적 LLM 질의를 요청했을 때, 토큰이 실시간 스트리밍으로 화면에 점진 렌더링되고, **추론이 완료되는 즉시 출처(Sources), 상태 배지, 후속 추천 질문 버튼이 매끄럽게 활성화**되어 대화를 계속 이어갈 수 있어야 합니다.

**Why this priority**: 스트리밍 생성 중에는 빠른 시각적 피드백을 제공하고, 생성이 끝난 후에는 공식 출처와 후속 액션 버튼을 즉시 연결해야 사용자가 다음 분석 단계로 단절 없이 이동할 수 있습니다.

**Independent Test**:
- 스트리밍 토큰 출력이 끝난 직후, 하단에 근거 출처 칩과 후속 질문 버튼들이 정상적으로 노출되고 클릭 가능한 상태로 전환되는지 검증.

**Acceptance Scenarios**:

1. **Given** 동적 LLM 생성 요청, **When** 백엔드 GPU가 토큰을 생성하기 시작하면, **Then** 첫 토큰부터 실시간 스트림으로 프론트엔드에 전달되어 타이핑 효과로 즉각 화면에 표시된다.
2. **Given** 토큰 생성이 완료된 시점(`type: "done"` 수신), **When** 스트림이 종료되면, **Then** 전체 텍스트의 마크다운이 최종 확정되고 출처 칩 및 후속 질문 네비게이션 버튼이 화면에 즉시 렌더링된다.

---

### User Story 3 - 타 챗봇(올리챗, 올원챗) 무결성 보존 및 GPU 자원 경합 완화 (Priority: P1)

PILOS 챗봇의 스트리밍 및 캐시 최적화 작업을 진행한 후에도 B-Team의 올리챗(Chatbot A / Streamlit)과 올원챗(Chatbot B / FastAPI)이 기존과 동일하게 완벽히 동작해야 하며, Pilos의 GPU 낭비가 사라져 타 챗봇의 응답 안정성이 함께 향상되어야 합니다.

**Why this priority**: 통합 서비스 생태계에서 개별 서브시스템 간의 간섭이나 회귀 버그(Regression)를 방지하는 것은 헌법(Constitution Principle III)의 핵심 원칙입니다.

**Independent Test**:
- E2E 서비스 진단 스크립트 실행 시 올리챗(`https://ezenitac.duckdns.org/bteam/chata/`) 및 올원챗(`https://ezenitac.duckdns.org/bteam/chatb/`)의 모든 기능이 정상 작동(HTTP 200)하는지 확인.

**Acceptance Scenarios**:

1. **Given** Pilos 최적화 완료 후 통합 서비스 환경, **When** B-Team 올리챗(Streamlit) 및 올원챗(FastAPI)을 호출하면, **Then** Nginx 프록시 및 API 통신이 일체의 장애나 속도 저하 없이 100% 정상 응답한다.
2. **Given** 공유 모델 게이트웨이, **When** Pilos가 정본 캐시를 활용할 때, **Then** GPU 여유 자원이 확보되어 타 챗봇의 LLM 추론 대기 시간이 감소한다.

---

### User Story 4 - 사용자 취소 제어 및 안전 폴백 안내 (Priority: P2)

사용자가 스트리밍 생성 도중 다른 질문을 선택하거나 모달을 닫을 경우 즉각 요청을 중단(Abort)할 수 있어야 하며, 극단적 장애(120초 초과 또는 GPU OOM) 발생 시 명확한 폴백 안내 메시지와 재시도 버튼이 제공되어야 합니다.

**Why this priority**: 사용자가 불필요한 대기를 언제든 중단하고 통제할 수 있게 함으로써 체감 UX 품질을 극대화합니다.

**Independent Test**:
- 스트리밍 도중 "닫기" 또는 "다른 질문 선택" 시 프론트엔드 fetch가 즉시 abort되고 UI가 깨끗하게 리셋되는지 확인.

**Acceptance Scenarios**:

1. **Given** 스트리밍 생성 중인 상태, **When** 사용자가 다른 질문을 클릭하면, **Then** 이전 스트림 연결이 즉시 중단(Abort)되고 새로운 요청으로 전환된다.
2. **Given** 120초 타임아웃 또는 모델 서비스 다운 상황, **When** 실패 감지 시, **Then** '분석 요청을 처리하지 못했습니다 (404)' 대신 사용자가 이해하기 쉬운 안내 메시지와 [다시 시도] 버튼이 출력된다.

---

## Edge Cases

- **Nginx 프록시 버퍼링으로 인한 스트림 지연**: `proxy_buffering off;` 및 `text/event-stream` 헤더 설정을 통해 청크가 실시간으로 브라우저에 도달하도록 보장.
- **스트림 도중 연결 단절 (Network Drop)**: 클라이언트가 수신 중 끊긴 경우 그때까지 수신된 텍스트를 보존하고 "답변이 중단되었습니다" 안내와 함께 [이어서 다시 시도] 버튼 제공.
- **고정 종목 화면 경로 (`/api/stocks/<stock_code>/chat`)**: URL 라우팅과 Nginx 프록시 매핑을 일치시켜 404 라우팅 불일치 원천 방지.
- **GPU OOM 또는 일시 단절**: 오류 발생 시 404 대신 준비된 정본 지식 요약으로 자동 폴백 전환.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 시스템은 등록된 15개 서비스 지식 질문 블록에 대해 사전 검증된 정본 응답 캐시(Knowledge Cache)를 적용하여 **10초 이내(통상 1~3초)**에 완결된 답변을 반환해야 한다.
- **FR-002**: 시스템은 동적 LLM 질문 처리에 대해 SSE 스트리밍 프로토콜(`type: "token"`, `type: "done"`, `type: "error"`)을 구현하여 실시간으로 토큰을 전달해야 한다.
- **FR-003**: 시스템은 추론 완료 시점(`type: "done"`)에 최종 상태, 공식 출처(Sources), 경고(Warnings), 후속 질문(Follow-ups) 메타데이터를 클라이언트에 전송하여 UI를 완결 상태로 전환해야 한다.
- **FR-004**: 시스템은 로컬 LLM 호출(`CHAT_LLM_TIMEOUT_SECONDS`), 백엔드 클라이언트, Nginx 프록시의 타임아웃을 **최소 120초**로 확대 설정해야 한다.
- **FR-005**: 시스템은 `OpenAICompatibleLlmClient`의 무분별한 30초 단위 재시도 루프를 제거하고 단일 스트림 호출 완결성을 보장해야 한다.
- **FR-006**: 본 작업의 모든 코드 수정은 A-Team Pilos 내부에 격리 적용되어야 하며, B-Team의 올리챗(`bteam/chata/`), 올원챗(`bteam/chatb/`), 올리뷰 웹(`bteam/oliview/`)에 어떠한 사이드 이펙트나 장애도 유발하지 않아야 한다.
- **FR-007**: 챗봇 프론트엔드는 스트리밍 수신 중 사용자 취소(다른 질문 클릭, 패널 닫기) 시 `AbortController`로 즉각 연결을 중단해야 한다.

### Key Entities

- **KnowledgeResponseCache**: 15개 서비스 지식 질문 블록에 대한 정본 응답을 메모리에 보유하여 10초 이내 즉각 반환하는 캐시 엔티티
- **StreamingCompletionProtocol**: 토큰 스트리밍(`token`) 및 추론 완료 메타데이터(`done`)를 규정하는 통신 프로토콜 엔티티
- **ServiceIsolationGuard**: A-Team 및 B-Team 서브시스템 간 독립성을 보호하는 격리 가드레일 엔티티

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 서비스 지식 질문 블록 응답 완료 시간 **10초 이내 (목표: 1~3초)** 달성.
- **SC-002**: 동적 LLM 생성 시 첫 토큰 화면 출력 시간(Time To First Token) **5초 이내** 달성.
- **SC-003**: B-Team 올리챗, 올원챗 및 올리뷰 웹 서비스 정상 가동률 **100% (회귀 결함 0건)** 유지.
- **SC-004**: 조기 타임아웃 및 재시도 폭주로 인한 404/503 오류 발생률 **0.0%** 달성.
- **SC-005**: 챗봇 응답 성공률(정상 스트림 또는 정본 캐시 답변 제공 비율) **99.9% 이상** 유지.

---

## Assumptions

- 로컬 GPU(GTX 1070)는 스트리밍 모드에서 초기 토큰을 수 초 내에 방출할 수 있으며, 전체 답변 생성에 20~45초가 소요됨.
- 사전 정의된 15개 서비스 지식 블록은 정본 문서 기반으로 사전에 캐싱되어 GPU 호출 없이 즉시 응답이 가능함.
- Nginx 리버스 프록시는 HTTP 1.1 및 `proxy_buffering off;` 설정을 통해 실시간 청크 전송을 완벽히 지원함.
- A-Team과 B-Team은 완전히 독립된 서브시스템으로 분리되어 있어 Pilos 변경이 B-Team 소스코드에 영향을 주지 않음.
