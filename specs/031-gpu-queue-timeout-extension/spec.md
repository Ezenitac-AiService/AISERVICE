# Feature Specification: 031-gpu-queue-timeout-extension

**Feature Branch**: `031-gpu-queue-timeout-extension`  
**Created**: 2026-08-26  
**Status**: Draft  
**Input**: User description: "chat A에 먼저 질문하고 작업을 진행하는 중에 chat B에 질문을 했더니, B는 바로 대답을 시작했고, chat A는 나중에야 대답을 시작했어, 여러 작업이 들어올때에, 단일 GPU로 인한 타임아웃에 대한 예외 처리를 검토해, 그냥 타임아웃을 할게 아니라, 순번을 받아서 대기하고 있다는것을 모델 게이트웨이 컨테이너가 타임아웃 전에 반환을 하고, 그걸 받아서 대기를 연장해야 할거 같은데, 타당성 검토를 하는데, 2026년 8월 기순 최신 트랜드, 방법론, 기법등을 리서치해서 근거로 사용해"

---

## 1. Background & Technical Feasibility Research (2026 Standard)

### 1.1 배경 및 문제 정의
* **단일 GPU(8~11GB VRAM) 동시성 병목**: 단일 GPU 환경(RTX 3060/4060 등)에서 복수의 챗봇 서비스(Chat A, Chat B)가 동시에 LLM 추론을 요청할 경우, KV 캐시 메모리 및 동시 디코딩 슬롯의 한계로 인해 요청 간 경합(Head-of-Line Blocking)이 발생합니다.
* **고정 타임아웃(Hard Timeout)의 한계**: 클라이언트가 10~20초의 고정 타임아웃을 설정한 상태에서 이전 작업으로 인해 대기 큐에 머무를 경우, 실제 장애가 아님에도 단순 대기 시간 초과로 504/ReadTimeout 예외가 발생하여 사용자 경험(UX)이 심각하게 저하됩니다.
* **서비스 간 불공정성(Starvation)**: 특정 챗봇이 다중 타겟(2~3개 제품) 비교 질의로 긴 시간 GPU를 점유할 때, 다른 챗봇의 단일 질의가 기아 상태에 빠지거나 큐 순서가 역전되는 현상이 발생할 수 있습니다.

### 1.2 2026 최신 LLM 게이트웨이 표준 및 방법론 근거
1. **Dynamic Lease & Sliding-Window Heartbeat Extension (RFC 9110 / SSE Keep-Alive)**:
   * 2026년 LLM 서빙 표준(vLLM Production Gateway, SGLang Router, LiteLLM)에서는 클라이언트-게이트웨이 간 고정 타임아웃 대신 **슬라이딩 윈도우(Sliding Window) 활동 기반 타임아웃**을 적용합니다.
   * 게이트웨이가 큐 대기 중 주기적 SSE 하트비트(`: keepalive\n\n`) 및 큐 상태 이벤트(`event: queue_status`)를 스트리밍함으로써 프록시/클라이언트의 유휴 연결 끊김(Idle Timeout)을 원천 방지하고 클라이언트의 타임아웃 리스를 자동으로 연장합니다.
2. **Progressive Queue Status Notification**:
   * 게이트웨이는 요청이 큐에 진입하는 즉시 `{"queue_position": N, "estimated_wait_s": T, "active_slots": M}` 정보를 실시간 스트리밍으로 반환합니다.
   * 클라이언트(Streamlit, Web UI)는 이를 수신하여 사용자에게 "⏳ GPU 자원 대기 중 (대기 순번 1번 / 예상 대기 3.2초)"과 같은 투명한 실시간 대기 피드백을 제공합니다.
3. **Tenant-Aware Fair Queuing (공정 큐잉 - DRR / Fair-Share)**:
   * 단순 FIFO 대신 서비스 테넌트(Chat A, Chat B) 간 가중치 공정 큐잉을 적용하여, 한 서비스의 대량 요청이 다른 서비스의 단일 요청을 독점 차단(Starvation)하지 않도록 보장합니다.

---

## 2. User Scenarios & Testing *(mandatory)*

### User Story 1 - 큐 진입 시 순번 안내 및 타임아웃 자동 연장 (Priority: P1)

단일 GPU가 이전 요청(예: Chat A의 복합 비교 질의)을 처리 중인 상태에서 새로운 요청(예: Chat B의 추천 질의)이 들어왔을 때, 새로운 요청은 타임아웃 에러를 발생시키지 않고 큐에 안전하게 대기하며 자신의 순번 및 예상 대기 시간을 실시간으로 수신받아 대기 시간을 자동으로 연장합니다.

* **Why this priority**: 다중 사용자/다중 서비스 동시 요청 시 발생하는 불필요한 타임아웃 장애를 제거하고 서비스 가용성을 보장하는 핵심 기능입니다.
* **Independent Test**: GPU가 10초간 추론 중인 상태에서 5초 타임아웃을 가진 클라이언트가 요청을 보냈을 때, 큐 하트비트를 통해 타임아웃 없이 순번을 수신하고 정상적으로 최종 답변을 생성하는지 검증.
* **Acceptance Scenarios**:
  1. **Given** GPU가 슬롯 최대치(Max Slots)로 연산 중인 상태에서, **When** 신규 LLM 요청이 도착하면, **Then** 모델 게이트웨이는 `event: queue_status`로 현재 대기 순번(예: 1번)과 예상 대기 시간을 1초 이내에 전송 시작해야 한다.
  2. **Given** 클라이언트가 큐 상태 이벤트를 수신 중일 때, **When** 대기 시간이 기본 타임아웃(예: 5초)을 초과하더라도, **Then** 하트비트 수신에 의해 클라이언트 타임아웃 타이머가 리셋(슬라이딩 갱신)되어 연결이 유지되어야 한다.
  3. **Given** 앞선 GPU 작업이 완료되면, **When** 대기 중인 요청이 추론 슬롯을 획득하면, **Then** `event: queue_status` (status: active)로 전환된 후 실시간 토큰 생성이 즉시 시작되어야 한다.

---

### User Story 2 - 실시간 대기 상태 UI 시각화 (Priority: P2)

챗봇 사용자(Chat A 및 Chat B)는 GPU가 혼잡하여 답변 생성이 즉시 시작되지 않을 때, 멈춘 것처럼 보이는 대신 실시간으로 업데이트되는 대기 순번과 예상 소요 시간을 확인하여 안심하고 대기할 수 있습니다.

* **Why this priority**: 긴 대기 시간 동안 사용자가 페이지를 이탈하거나 반복해서 새로고침하는 UX 저하를 방지합니다.
* **Independent Test**: 동시 다발 질의를 인입시키고 Streamlit(Chat A) 및 웹 UI(Chat B)의 상태 컨테이너에 "⏳ 대기 순번 1번 (약 3초 예상)" 뱃지가 실시간 렌더링되는지 확인.
* **Acceptance Scenarios**:
  1. **Given** 사용자가 질문을 전송하고 요청이 큐에 대기할 때, **When** 게이트웨이로부터 `queue_status`를 수신하면, **Then** UI의 진행 컨테이너가 `대기 순번: N번 (예상: T초)` 형태로 실시간 업데이트되어야 한다.
  2. **Given** 대기 순번이 2번에서 1번으로 줄어들 때, **When** 게이트웨이가 갱신된 순번 이벤트를 보내면, **Then** UI에 즉시 반영되어야 한다.

---

### User Story 3 - 테넌트 간 공정 스케줄링 (Fair Queuing) (Priority: P3)

Chat A와 Chat B가 동시에 여러 요청을 보낼 때, 특정 챗봇의 긴 질의가 큐를 독점하지 않고 테넌트 간 번갈아가며 공정하게 GPU 슬롯을 배정받습니다.

* **Why this priority**: 다중 서비스 생태계에서 특정 서비스의 기아(Starvation) 현상을 방지합니다.
* **Independent Test**: Chat A에서 3개의 연속 질의를 넣은 직후 Chat B에서 1개의 질의를 넣었을 때, Chat B 질의가 Chat A의 모든 3개 질의가 끝날 때까지 무한정 밀리지 않고 공정하게 배정되는지 검증.
* **Acceptance Scenarios**:
  1. **Given** 테넌트 A가 큐에 다수의 작업을 적재한 상황에서, **When** 테넌트 B의 요청이 인입되면, **Then** 공정 큐 스케줄러가 테넌트 B의 우선순위를 조정하여 기아 현상을 방지해야 한다.

---

### Edge Cases
- **클라이언트 중도 이탈(Disconnect)**: 큐에 대기 중이던 클라이언트가 브라우저 탭을 닫으면, 게이트웨이가 `request.is_disconnected()`를 감지하여 즉시 큐에서 제거하고 GPU 자원 낭비를 방지한다.
- **예상치 못한 GPU 크래시/OOM**: 큐 대기 중 백엔드 엔진이 비정상 종료될 경우, 게이트웨이가 재기동(Self-healing) 상태를 클라이언트에 알리고 대기 시간을 보정한다.
- **최대 큐 용량 초과**: 큐 대기 수가 안전 한계치(예: 30개)를 초과할 경우, 무한 대기 대신 HTTP 429 (Retry-After)로 안전하게 차단한다.

---

## 3. Requirements *(mandatory)*

### Functional Requirements

* **FR-001 (Gateway Queue Controller)**: 모델 게이트웨이(`model_gateway`)는 단일 GPU 동시 처리 한도(기본 `active_slots=1~2`)를 초과하는 요청에 대해 비동기 우선순위 대기 큐(`AsyncFairQueue`)를 운영해야 한다.
* **FR-002 (SSE Heartbeat & Queue Stream)**: 게이트웨이는 요청이 큐에 진입한 즉시 HTTP 200 SSE 스트림을 오픈하고, 최소 1.5초 간격으로 `event: queue_status` 또는 `: keepalive` 하트비트를 클라이언트에 지속 전송해야 한다.
* **FR-003 (Queue Status Payload)**: `queue_status` 이벤트는 `queue_position`(대기 순번, 정수), `estimated_wait_sec`(예상 대기 초, 실수), `active_requests`(현재 연산 중인 요청 수), `timestamp` 필드를 포함해야 한다.
* **FR-004 (Client Sliding-Window Timeout)**: 챗봇 코어 클라이언트(`AiGatewayClient`)는 고정 타이머 대신 **마지막 수신 패킷 기준 슬라이딩 윈도우 타임아웃**을 적용하여, 하트비트가 수신되는 동안에는 타임아웃 예외를 발생시키지 않고 대기 리스를 자동 연장해야 한다.
* **FR-005 (Chat A Streamlit Queue UX)**: `StreamlitGraphAdapter` 및 `06.02.app.py`는 `queue_status` 수신 시 `st.status()` 상태 라벨을 `⏳ GPU 대기 중 (순번 N번, 약 T초 예상)`으로 실시간 업데이트해야 한다.
* **FR-006 (Chat B Web UI Queue UX)**: `project_ragapi.py` 및 `index.html`은 `queue_status` 수신 시 타임라인 상단 뱃지를 `⏳ 대기 순번: N번 (예상 T초)`으로 실시간 변경하고 대기 애니메이션을 유지해야 한다.
* **FR-007 (Tenant Fair Scheduling)**: 게이트웨이 스케줄러는 요청 헤더(`X-Tenant-Id` 또는 클라이언트 식별자)를 기반으로 Deficit Round Robin(DRR) 공정 큐잉을 적용하여 서비스 간 기아를 방지해야 한다.
* **FR-008 (Client Disconnect Purge)**: 큐에 대기 중인 요청의 클라이언트 연결이 끊어지면, 게이트웨이는 해당 요청을 큐에서 즉시 제거(Purge)해야 한다.
* **FR-009 (Max Queue Capacity Guard)**: 큐 크기가 임계치(기본 30건)를 초과할 경우 즉시 HTTP 429(Too Many Requests)와 `Retry-After: 5`를 반환해야 한다.
* **FR-010 (Hot-Swap / Non-Streaming Compatibility)**: 비스트리밍 단일 요청(`stream=false`)의 경우에도 큐 진입 시 `X-Queue-Position` 헤더 또는 폴링/SSE 업그레이드 지원을 통해 타임아웃을 안전하게 관리해야 한다.

---

### Key Entities

* **`QueueTicket`**: 큐에 진입한 개별 요청의 상태 관리 객체.
  * 속성: `request_id`, `tenant_id`, `created_at`, `priority`, `estimated_duration_s`, `client_disconnected_event`
* **`QueueStatusEvent`**: 클라이언트에 스트리밍되는 실시간 큐 상태 이벤트.
  * 속성: `event_type ("queue_status")`, `queue_position`, `estimated_wait_sec`, `active_slots`, `timestamp`
* **`TenantProfile`**: 서비스 테넌트(Chat A, Chat B 등)별 공정 큐잉 메타데이터.
  * 속성: `tenant_id`, `current_active_requests`, `queued_requests_count`, `last_served_at`

---

## 4. Success Criteria *(mandatory)*

### Measurable Outcomes

* **SC-001 (동시 요청 타임아웃 0건 달성)**: Chat A와 Chat B에서 동시 3건 이상의 요청이 인입될 때, GPU 연산 지연으로 인한 504 / ReadTimeout 예외 발생률 **0.0%**.
* **SC-002 (초기 큐 피드백 지연 시간)**: 큐 진입 후 첫 번째 `queue_status` 이벤트가 클라이언트에 전달되기까지의 시간 **< 200ms**.
* **SC-003 (하트비트 신뢰성)**: 대기 중 최소 **1.5초마다 1회 이상** 하트비트/큐 이벤트가 전송되어 프록시 및 브라우저의 유휴 연결 끊김 방지.
* **SC-004 (테넌트 공정성)**: 연속된 긴 질의 환경에서 다른 테넌트의 단일 질의 대기 시간이 직전 요청 완료 시간 이상으로 지연되지 않음(기아 현상 0건).
* **SC-005 (자원 누수 방지)**: 클라이언트 탭 닫힘 시 큐 내 잔여 요청이 **1.0초 이내**에 즉시 메모리에서 제거됨.

---

## 5. Assumptions & Dependencies

* **하드웨어 제약**: 시스템은 1개의 물리 GPU(VRAM 8~11GB) 환경을 기준으로 하며, LLM 모델은 `qwen3.5-2b` 단일 상주 모드로 동작한다.
* **통신 프로토콜**: 모든 LLM 추론 통신은 SSE(Server-Sent Events) 스트리밍 프로토콜을 기본으로 한다.
* **하위 호환성**: OpenAI 표준 API 포맷(`POST /v1/chat/completions`)의 규격을 손상시키지 않고, 표준 SSE 스트림 내의 커스텀 이벤트(`event: queue_status`) 및 코멘트(`: keepalive`) 형태로 확장한다.
