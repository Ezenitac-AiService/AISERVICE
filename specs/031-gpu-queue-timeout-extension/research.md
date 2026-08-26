# Phase 0 Research & Technology Decisions: 031-gpu-queue-timeout-extension

**Feature**: `031-gpu-queue-timeout-extension`  
**Date**: 2026-08-26  
**Status**: Completed  

---

## 1. Research Questions & Decisions

### Decision 1: Queue Controller & Slot Management Architecture
* **Decision**: `AsyncFairQueue`를 `model_gateway/src/core/queue_manager.py`에 싱글톤으로 구현하며, 세마포어 기반의 가변 슬롯(Variable Slots) 메커니즘을 적용한다.
* **Slot Capacity**:
  * 기본 설정: `active_slots=1` (`MAX_GPU_CONCURRENT_SLOTS=1`, 8~11GB 단일 GPU OOM 0% 안전성 보장)
  * 가변 확장: 환경변수 또는 하드웨어 프로필에 따라 `active_slots=N`으로 동적 확장 가능.
* **Rationale**:
  * 단일 GPU 환경(RTX 3060/4060, 8~11GB VRAM)에서는 `qwen3.5-2b` 모델의 KV 캐시 점유와 동시 디코딩 부하를 통제하기 위해 단일 슬롯(`active_slots=1`) 순차 처리가 가장 안전합니다.
  * 동시에 아키텍처는 가변 슬롯 구조로 설계되어 향후 고사양 GPU(24GB+) 또는 멀티 GPU 환경으로 이전 시 설정 변경만으로 즉시 병렬 처리가 가능합니다.
* **Alternatives Considered**:
  * *FIFO Unbounded Queue*: 선입선출만 처리할 경우 한 테넌트의 연속 질의가 다른 테넌트를 독점 차단(Starvation)하는 문제가 있어 기각.
  * *Static Multi-Slot (Fixed 2)*: 단일 8GB VRAM에서 긴 컨텍스트 2개 동시 처리 시 OOM 위험이 있어 기각.

---

### Decision 2: SSE Keep-Alive & Event-Driven Queue Updates
* **Decision**:
  1. **큐 진입 즉시 SSE 스트림 오픈**: HTTP 200 `text/event-stream`을 즉시 응답하여 클라이언트와 TCP/HTTP 연결을 체결.
  2. **큐 상태 이벤트 (`event: queue_status`)**:
     * 상태 변경 시 (앞선 작업 완료로 순번 $N \to N-1$ 변경) 즉시(Event-Driven, <100ms) 전송.
     * 상태 변경이 없더라도 UI 대기 카운트다운 동기화를 위해 3~5초 주기로 갱신 이벤트 전송.
  3. **인프라 Keep-Alive 하트비트 (`: keepalive\n\n`)**: 15초 주기로 전송하여 Nginx, Cloudflare, ALB의 60초 유휴 타임아웃 방지.
* **Rationale**:
  * 2026년 프로덕션 LLM 서빙 표준(vLLM, LiteLLM, AWS ALB)에서 권장하는 하트비트 골든 스탠다드는 **15초**입니다. 1.5초는 네트워크 패킷과 CPU 오버헤드가 과도하며, 30초 이상은 모바일/방화벽 타임아웃 위험이 있습니다.
* **Alternatives Considered**:
  * *1.5초 고정 하트비트*: 불필요한 패킷 과다 발생 및 CPU Context Switch 낭비로 기각.
  * *Polling (HTTP 202 + GET /status)*: 매 초 폴링으로 인한 불필요한 HTTP 왕복 오버헤드 발생으로 기각.

---

### Decision 3: Client Inactivity Sliding-Window Timeout Lease
* **Decision**: `AiGatewayClient` 및 B-Team RAG 클라이언트의 타임아웃 정책을 고정 20초 Hard Timeout에서 **"마지막 바이트/이벤트 수신 후 15초 무응답 시 타임아웃(Sliding Inactivity Timeout)"**으로 전환한다.
* **Rationale**:
  * 큐 대기 시간이 30~40초로 길어지더라도 게이트웨이가 15초마다 생존 신호(`: keepalive`)나 큐 갱신 이벤트를 제공하면 클라이언트는 정상적으로 대기를 연장합니다.
  * 게이트웨이 프로세스 자체가 다운되어 진짜 무응답 상태가 된 경우에만 15초 후 `ReadTimeout`을 발생시켜 안전하게 복구합니다.
* **Alternatives Considered**:
  * *전체 Hard Timeout 60초로 단순 증가*: 진짜 다운되었을 때 사용자가 60초 동안 에러 없이 멍하니 기다려야 하므로 기각.

---

### Decision 4: Tenant-Aware Fair Scheduling (DRR / Deficit Round Robin)
* **Decision**: 서비스 테넌트 식별자(`X-Tenant-Id: chata` 또는 `chatb`)를 기반으로 테넌트별 큐를 분리하고, Deficit Round Robin 방식으로 교차 스케줄링한다.
* **Rationale**:
  * Chat A에서 복합 비교 질의 3건을 연속으로 인입시킨 직후 Chat B에서 1건의 질문을 보냈을 때, Chat B가 Chat A의 3건이 모두 끝날 때까지 40초간 대기하는 불공정(Starvation)을 방지합니다.
* **Alternatives Considered**:
  * *Strict Priority*: 특정 테넌트(예: Chat A)에 고정 우선순위를 주면 다른 테넌트가 영구 기아 상태에 빠지므로 기각.

---

### Decision 5: Request Coalescing (멱등성 스트림 멀티플렉싱) & Client Disconnect Purge
* **Decision**:
  1. **Request Coalescing**: 동일한 세션에서 5초 이내 동일 프롬프트(`session_id` + `prompt_hash`)가 중복 인입될 경우, 신규 큐 슬롯을 배정하지 않고 기존 큐 티켓의 출력 채널에 멀티플렉싱 연결한다.
  2. **Disconnect Purge**: 대기 중 브라우저 탭 닫힘(`request.is_disconnected()`) 또는 UI `[대기 취소]` 버튼 클릭 시 1.0초 이내에 큐에서 즉시 방출하고 GPU 자원을 회수한다.
* **Rationale**:
  * 사용자의 더블 클릭이나 네트워크 불안정으로 인한 재전송 시 GPU 슬롯이 이중 낭비되는 것을 방지합니다.
  * 중도 이탈한 요청이 GPU를 점유하여 뒤따르는 정상 사용자들의 대기 시간을 늘리는 문제를 방지합니다.
