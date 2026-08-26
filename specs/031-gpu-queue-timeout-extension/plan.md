# Implementation Plan: 031-gpu-queue-timeout-extension

**Branch**: `031-gpu-queue-timeout-extension` | **Date**: 2026-08-26 | **Spec**: [`spec.md`](file:///c:/AISERVICE/specs/031-gpu-queue-timeout-extension/spec.md)

**Input**: Feature specification from `/specs/031-gpu-queue-timeout-extension/spec.md`

---

## 1. Summary

단일 GPU(8~11GB VRAM, RTX 3060/4060) 환경에서 복수 챗봇(Chat A, Chat B)의 동시 LLM 요청 인입 시 발생하는 큐 경합과 타임아웃 장애를 해결합니다.
2026년 프로덕션 서빙 표준에 맞춰 **가변 슬롯(Variable-Slot) 비동기 공정 큐(`AsyncFairQueue`)**, **SSE 15초 Keep-Alive 하트비트**, **Event-Driven 큐 순번 통보**, **슬라이딩 무응답 타임아웃(Sliding Inactivity Timeout)**, **클라이언트 대기 취소(Cancel) 인터랙션**, **중복 요청 병합(Request Coalescing)**을 통합 구현합니다.

---

## 2. Technical Context

* **Language/Version**: Python 3.12, FastAPI 0.115+, Uvicorn 0.32+, Streamlit 1.40+
* **Primary Dependencies**: `asyncio`, `httpx` (0.28+), `fastapi`, `sse-starlette`, `redis`, `pydantic`
* **Storage**: Redis 7.2 (Queue Metadata & L1~L3 Cache), MySQL 8.0 (Oliveyoung Products Master)
* **Testing**: `pytest`, `httpx` async test suite, Multi-client Concurrency Stress Test
* **Target Platform**: Docker Linux Container (`aiservice-model-gateway`, `oliview_chatbot_a`, `oliview_chatbot_b`)
* **Project Type**: Distributed Web Service & AI Inference Gateway
* **Performance Goals**:
  * 동시 다발 질의 시 타임아웃 에러율: **0.0%**
  * 큐 진입 시 첫 `queue_status` 지연 시간: **< 200ms**
  * 사용자 취소 시 큐 Purge 시간: **< 1.0초**
* **Constraints**:
  * 단일 GPU 8~11GB VRAM 환경 기본 `active_slots=1` (OOM 0% 안전성 보장)
  * OpenAI 호환 규격(`POST /v1/chat/completions`) 100% 보존
* **Scale/Scope**:
  * Chat A (Streamlit) & Chat B (Web UI) 멀티 테넌트 실시간 서빙

---

## 3. Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Compliance Assessment | Status |
|---|---|:---:|
| **I. 언어 및 커뮤니케이션** | 모든 명세, 설계, 주석, UI 상태 메시지는 한국어 표기 | ✅ PASS |
| **II. TDD 및 계약 검증** | SSE 프로토콜 계약(`contracts/queue_sse_contract.md`) 및 동시성 시나리오 선행 구축 | ✅ PASS |
| **III. 서비스 격리 및 무결성** | `model_gateway`, `oliview_chatbot_a`, `oliview_chatbot_b` 격리 및 기존 모델/DB 보존 | ✅ PASS |
| **IV. 구조화된 로깅** | 큐 진입, 슬롯 획득, 순번 변동, 하트비트 전송 로그를 JSON/구조화 로깅으로 기록 | ✅ PASS |
| **V. YAGNI & 점진적 진화** | 가변 슬롯 아키텍처를 단순 세마포어로 구현하고 현재 단일 슬롯(`active_slots=1`) 기본 운영 | ✅ PASS |

---

## 4. Project Structure & Changes

### Documentation
```text
specs/031-gpu-queue-timeout-extension/
├── plan.md              # This file
├── research.md          # Phase 0 decisions (15s Keep-Alive, Sliding Timeout, Fair DRR)
├── data-model.md        # QueueTicket, QueueStatusPayload, TenantProfile
├── quickstart.md        # Concurrency & Cancel Verification Scenarios
├── contracts/           # SSE Stream & Cancel API Contract
│   └── queue_sse_contract.md
└── checklists/
    └── requirements.md  # 12/12 Checked
```

### Source Code Changes

#### 1) Model Gateway Component (`model_gateway/`)
* **[NEW] [`src/core/queue_manager.py`](file:///c:/AISERVICE/model_gateway/src/core/queue_manager.py)**:
  * `AsyncFairQueue` 싱글톤 클래스 구현 (가변 슬롯 `active_slots=1` 세마포어, DRR 공정 큐잉, Request Coalescing, 15초 Keep-Alive 타이머).
  * `QueueTicket` 관리 및 `request.is_disconnected()` 비동기 리스너 탑재.
* **[MODIFY] [`src/api/routes/inference_api.py`](file:///c:/AISERVICE/model_gateway/src/api/routes/inference_api.py)**:
  * `/v1/chat/completions` 스트림 핸들러에 `AsyncFairQueue.enqueue()` 연동.
  * 큐 대기 중 `event: queue_status` 및 `: keepalive\n\n` 주입.
  * **[NEW ENDPOINT]** `POST /v1/queue/cancel` 큐 즉시 방출 API 추가.

#### 2) B-Team Core Component (`bteam/oliview_core/`)
* **[MODIFY] [`client.py`](file:///c:/AISERVICE/bteam/oliview_core/client.py)**:
  * `AiGatewayClient.generate_stream`: 슬라이딩 무응답 타임아웃(`read=15.0s`, `timeout=None`) 적용.
  * SSE 수신 루프에서 `event: queue_status` 파싱 및 콜백 핸들러에 전송.
* **[MODIFY] [`callback.py`](file:///c:/AISERVICE/bteam/oliview_core/callback.py) & [`graph_orchestrator.py`](file:///c:/AISERVICE/bteam/oliview_core/graph_orchestrator.py)**:
  * `StepEvent`에 `QUEUE_WAITING` 상태 추가 및 실시간 순번/대기 시간 브로드캐스팅.

#### 3) Chat A (Streamlit) Component (`bteam/Oliview_chatbot_a/`)
* **[MODIFY] [`graph_adapter.py`](file:///c:/AISERVICE/bteam/Oliview_chatbot_a/graph_adapter.py)**:
  * `queue_status` 이벤트 수신 시 `status_container.update(label="⏳ GPU 자원 대기 중 (순번 N번, 약 T초 예상)")` 렌더링.
* **[MODIFY] [`06.02.app.py`](file:///c:/AISERVICE/bteam/Oliview_chatbot_a/06.02.app.py)**:
  * 대기 중 `[대기 취소]` 버튼 인터랙션 제공 및 세션 정리.

#### 4) Chat B (Web UI / FastAPI) Component (`bteam/Oliview_chatbot_b/`)
* **[MODIFY] [`project_ragapi.py`](file:///c:/AISERVICE/bteam/Oliview_chatbot_b/project_ragapi.py)**:
  * SSE 제너레이터에 `event: queue_status` 브릿지 및 취소 라우터 추가.
* **[MODIFY] [`index.html`](file:///c:/AISERVICE/bteam/Oliview_chatbot_b/index.html)**:
  * 상단 타임라인 컨테이너에 `⏳ 대기 순번: N번 (예상: T초)` 뱃지 및 `[대기 취소]` 버튼 연동.

---

## 5. Verification Plan

1. **단위 테스트**:
   * `AsyncFairQueue` 락 획득/반환, 동시성 슬롯 제한, DRR 공정 배분, Request Coalescing 테스트.
2. **E2E 동시성 스트레스 테스트**:
   * Chat A와 Chat B에서 동시 3개 이상 질의 인입 후 504 / ReadTimeout 0건 통과 확인.
3. **취소 및 연결 끊김 테스트**:
   * 큐 대기 중 취소 시 1.0초 이내 GPU 자원 회수 및 다음 대기자 즉시 진입 확인.
