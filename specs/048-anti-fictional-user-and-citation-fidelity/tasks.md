# Implementation Tasks: 048-anti-fictional-user-and-citation-fidelity

**Feature Branch**: `048-anti-fictional-user-and-citation-fidelity`
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)
**Status**: Blocked until Phase 1 contracts and Phase 2 Red tests are approved

---

## Execution Rules

- Phase 3 이후 구현 태스크는 T001~T015의 계약·실패 테스트가 완료되고 Red 결과가 기록되기 전에는 시작하지 않는다.
- 무효 인용은 제거한다. 다른 유효 번호로 clamping하거나 근거를 재지정하지 않는다.
- `StreamingTokenInterceptor`는 호환 이름이며 UTF-8로 디코딩된 text chunk와 동적 carry buffer를 처리한다. 고정 3/4-token 가정을 사용하지 않는다.
- `0.85/0.60/0.25`는 초기 평가 후보값이다. T040 승인 결과 없이 운영 상수로 확정하지 않는다.
- `sync_core.py` write mode는 dry-run, hash manifest, 원자적 교체, 충돌 차단 테스트가 Green인 경우에만 실행한다.

---

## Phase 1: Governance, Contracts & Baselines

**Purpose**: 계약 우선주의와 재현 가능한 평가 기준을 구현 전에 확정한다.

- [ ] T001 [P] `contracts/core_prompt_contract.json`, `contracts/chat_api_contract.json`, `contracts/chat_api_response_contract.json`, `contracts/sse_event_contract.json`, `contracts/structured_log_contract.json`, `contracts/changelog_schema.json`의 Draft 2020-12 계약을 검토·승인한다 (FR-003, FR-004, FR-018~FR-023).
- [ ] T002 [P] `bteam/oliview_core/tests/test_contracts_and_logging.py`에 모든 계약의 schema validation 및 대표 valid/invalid fixture 테스트를 작성하고 구현 미연결로 인한 Red 결과를 기록한다 (FR-021, FR-022).
- [ ] T003 [P] `bteam/oliview_core/tests/test_config_ssot.py`에 환경변수 필수성, 외부 vLLM 기본 비활성화, endpoint 누락, 셀프 루프백·포트 충돌 차단 테스트를 작성하고 Red를 기록한다 (FR-023).
- [ ] T004 [P] `bteam/oliview_core/tests/test_structured_logging.py`에 correlation ID, latency, model invocation, abstention, guardrail 필드와 query/review/token/secret 비기록·마스킹 테스트를 작성하고 Red를 기록한다 (FR-019, FR-022, SC-010).
- [ ] T005 [P] `bteam/oliview_core/tests/test_sync_core_safety.py`에 dry-run, source/destination hash, 예상치 못한 변경 거부, 원자적 교체 실패 복구 테스트를 작성하고 Red를 기록한다 (Constitution III).
- [ ] T006 `bteam/oliview_core/tests/fixtures/feature_048_eval_cases.json`에 정상·희소·부정·혼합·중복·K=0·prompt injection·PII·XSS·Unicode/SSE split 평가 케이스와 고정 seed를 정의한다 (SC-001~SC-005, SC-009).
- [ ] T007 `tests/hardware_workloads/feature_048.json`에 모델 해시, quant, context pool, slot, prompt/output 길이, 동시성, 반복 횟수, GPU/driver/server version 기록 형식을 정의한다 (SC-011).

**Checkpoint**: 계약과 baseline만 확정된 상태다. 구현은 아직 시작하지 않는다.

---

## Phase 2: Failing Tests (Red Gate)

**Purpose**: 모든 신규 기능과 보안 경계를 실패 테스트로 먼저 고정한다.

- [ ] T008 [P] [US1] `bteam/Oliview_chatbot_a/tests/test_anti_hallucination_a.py`에 가상 라벨, 원문 불일치 직접 인용, 객관 요약 대체 테스트를 작성하고 Red를 확인한다 (FR-002, FR-003, SC-001).
- [ ] T009 [P] [US1] `bteam/Oliview_chatbot_b/tests/test_anti_hallucination_b.py`에 동일 방어와 레거시 IT prompt 비노출 테스트를 작성하고 Red를 확인한다 (FR-002, FR-010, SC-001, SC-005).
- [ ] T010 [P] [US1] `bteam/oliview_core/tests/test_exact_quote_fidelity.py`에 Unicode normalization 정책을 포함한 exact-match quote 및 불일치 인용 제거·요약 대체 테스트를 작성한다 (FR-003).
- [ ] T011 [P] [US2] `bteam/oliview_core/tests/test_citation_bounds_and_abstention.py`에 `K=0/1/Kmax`, `N<1`, `N>K`, malformed citation, 무보정 제거, K=0 모델 무호출 테스트를 작성한다 (FR-004, FR-007, SC-003, SC-005).
- [ ] T012 [P] [US2] `bteam/Oliview_chatbot_b/tests/test_polarity_fidelity_b.py`에 긍정·부정·혼합 평가 케이스와 극성 반전 테스트를 작성한다 (FR-005, SC-004).
- [ ] T013 [P] [US3] `bteam/oliview_core/tests/test_stream_boundary_safety.py`에 금지 문자열의 모든 문자 경계, 대표 SSE event 경계, 잘못된 UTF-8·finalize·reconnect 테스트를 작성한다 (FR-006, SC-002).
- [ ] T014 [P] `bteam/oliview_core/tests/test_prompt_injection_and_redaction.py`에 직접·간접·다국어·난독화 prompt injection, PII·credential redaction 테스트를 작성한다 (FR-018, FR-019, SC-009).
- [ ] T015 [P] `bteam/oliview_core/tests/test_api_limits_and_sse.py` 및 프론트엔드 보안 테스트에 인증, query/output 상한, timeout, rate limit, 오류/SSE schema, HTML·event handler·javascript URL 비실행 테스트를 작성한다 (FR-020, FR-021, SC-009).

**Checkpoint**: T002~T005 및 T008~T015의 예상 실패가 기록되고 사용자 승인된 경우에만 Phase 3으로 진행한다.

---

## Phase 3: Core Green Implementation

**Purpose**: 승인된 Red 테스트를 최소 구현으로 Green 전환한다.

- [ ] T016 `bteam/oliview_core/config.py`에 포트·모델 URL·healthcheck·mode·검색 후보값을 환경변수 기반 SSOT로 구현하고 외부 vLLM opt-in 및 셀프 루프백을 차단한다 (T003, FR-023).
- [ ] T017 `bteam/oliview_core/logging.py`에 구조화 로그, correlation ID, latency/model/abstention/guardrail 이벤트 및 민감 원문 비기록·마스킹을 구현한다 (T004, FR-019, FR-022).
- [ ] T018 `bteam/oliview_core/prompts.py`에 공통 integrity 규칙, 비신뢰 context 구획, `PersonaType.CONCIERGE/ANALYST` 어댑터를 구현한다 (T008, T009, T014, FR-001, FR-002, FR-018).
- [ ] T019 `bteam/oliview_core/guardrail.py`에 가상 라벨 제거, exact quote 검증, `1 <= N <= K` 이외 인용 제거, polarity 검증과 기권 결과를 구현한다. 인용 clamping은 금지한다 (T010~T012, FR-003~FR-005).
- [ ] T020 `bteam/oliview_core/nodes/synthesis_node.py`에 UTF-8 decoded chunk 및 금지 패턴 최대 접두어 길이 기반 carry buffer를 구현하고 최종 sanitizer를 결합한다 (T013, FR-006).
- [ ] T021 `bteam/oliview_core/utils/document_top_p.py`에 설정 기반 threshold/cliff 후보값, `0 <= K <= configured max <= 20`, K=0 모델 무호출 기권을 구현한다 (T011, FR-007, FR-012).
- [ ] T022 `bteam/sync_core.py`에 dry-run, hash manifest, allowlisted destination, 원자적 교체와 충돌 거부를 구현하여 T005를 Green으로 전환한다.
- [ ] T023 [P] `bteam/oliview_core/__init__.py`에 필요한 public API를 export하고 직접 master import가 가능한 서비스는 복제본 대신 master/package를 사용하도록 정리한다 (FR-001).
- [ ] T024 `bteam/sync_core.py --dry-run` 결과를 검토한 뒤 write sync를 한 번 실행하고 source/destination hash 일치를 기록한다.

**Checkpoint**: core 계약·integrity·security·logging·sync 테스트 Green.

---

## Phase 4: User Story 1~4 Application Integration

### ChatA — Concierge and Mobile-first

- [ ] T025 [US1][US4] ChatA 진입점에 `PersonaType.CONCIERGE`, 공통 contract와 K=0 기권 응답을 연결한다 (FR-008).
- [ ] T026 [P][US4] `bteam/Oliview_chatbot_a/static/css/style.css`에 `100dvh`, `85svh`, 48px target, visible/non-obscured focus와 360/375/390/414/768/1024px 레이아웃을 구현한다 (FR-009, FR-017).
- [ ] T027 [P][US4] `bteam/Oliview_chatbot_a/static/js/chat_ui.js`에 `visualViewport`, accessible dialog/status, safe text sink 또는 allowlist sanitizer, SSE reconnect 중 미검증 partial output 폐기를 구현한다 (FR-009, FR-020).
- [ ] T028 [US1][US4] ChatA tests를 Green으로 전환하고 모바일·보안 회귀 테스트를 통과시킨다.

### ChatB — Analyst and Adaptive Dashboard

- [ ] T029 [US3] `bteam/Oliview_chatbot_b/common.py`와 prompt 구성 함수에서 `NO_THINK_SYSTEM_PROMPT`를 제거하고 `PersonaType.ANALYST`를 연결한다 (FR-010).
- [ ] T030 [US3] `bteam/Oliview_chatbot_b/project_ragapi.py`의 스트리밍 prompt 구성 함수를 심볼 기준으로 교체하고 request/response/SSE contracts를 적용한다. 특정 라인 번호에 의존하지 않는다 (FR-010, FR-021).
- [ ] T031 [US4] `/api/brands`와 Chat API에 인증, timeout, input/output limit, rate limit, 안전한 오류 응답을 적용한다 (FR-021).
- [ ] T032 [P][US4] `bteam/Oliview_chatbot_b/index.html`에 `document_score_threshold`, `cliff_delta`, max selected reviews, score bars, `<768`, `768~1023`, `>=1024` adaptive layout과 안전한 DOM 렌더링을 구현한다 (FR-011~FR-013, FR-020).
- [ ] T033 [US3][US4] ChatB tests와 stream boundary/security tests를 Green으로 전환한다.

---

## Phase 5: User Story 5 Portal & Changelog

- [ ] T034 [P][US5] `gateway/html/index.html`의 ChatA/ChatB 설명과 Engineering Evolution 2x1 hero card를 구현한다 (FR-014, FR-015).
- [ ] T035 [P][US5] `gateway/html/changelog.html`에 7개 milestone과 subsystem filter를 구현한다. `all`은 필터 상태로만 사용하고 milestone subsystem 값에는 저장하지 않는다 (FR-016).
- [ ] T036 [US5] 두 페이지의 동적 문자열을 safe sink로 렌더링하고 keyboard, focus, DOM order, dialog/status semantics, 48px target을 적용한다 (FR-017, FR-020).
- [ ] T037 [US5] changelog schema, filter, navigation, XSS 및 접근성 자동 테스트를 Green으로 전환한다 (SC-006, SC-007, SC-009).

---

## Phase 6: Evaluation, Performance & Live Verification

- [ ] T038 `pytest --collect-only -q`로 실제 baseline을 갱신한 뒤 `bteam/oliview_core/tests/`, ChatA tests, ChatB tests 전체를 실행해 수집된 테스트 100% PASS를 확인한다 (SC-008).
- [ ] T039 T006 고정 코퍼스를 반복 실행하여 가상 라벨, quote mismatch, invalid citation, polarity inversion, prompt injection, PII/XSS 결과와 claim/context metrics를 기록한다 (SC-001~SC-005, SC-009).
- [ ] T040 검색 후보값 `document_score_threshold=0.85`, second-score `0.60`, cliff `0.25`를 precision/recall, groundedness, abstention trade-off로 calibration하고 승인값을 `config.py` 환경 기본값 문서에 반영한다 (FR-007, FR-012).
- [ ] T041 `tests/test_hardware_concurrency.py`와 T007 workload로 GTX 1070 llama.cpp 및 RTX 2080/3060 후보 backend를 측정하고 모델 hash, quant, context pool, per-slot context, VRAM, TTFT, total latency, throughput, OOM을 기록한다 (SC-011).
- [ ] T042 환경변수 `BASE_URL`의 HTTPS endpoint에서 ChatA, ChatB, portal/changelog E2E와 HTTP→HTTPS, 인증 실패, SSE reconnect, 모바일 실기기 매트릭스를 검증한다 (SC-006, SC-007, FR-021, FR-023).
- [ ] T043 `specs/048-anti-fictional-user-and-citation-fidelity/verification-report.md`에 계약 버전, Red/Green 증거, 테스트 수, 평가 결과, threshold 승인, 보안 결과, hardware 결과와 미해결 위험을 기록한다.

---

## Dependencies & Execution Order

```text
Phase 1: Contracts & Baselines (T001~T007)
                 |
                 v
Phase 2: Failing Tests / RED (T008~T015)
                 |
                 v  USER APPROVAL GATE
Phase 3: Core GREEN (T016~T024)
                 |
                 +--------------------+
                 v                    v
Phase 4: ChatA/ChatB (T025~T033)   Phase 5: Portal (T034~T037)
                 +--------------------+
                                      v
Phase 6: Evaluation & Live Verification (T038~T043)
```

## Parallel Execution Opportunities

- T002~T007은 계약 T001 확정 후 병렬 가능하다.
- T008~T015는 fixture와 계약이 고정된 뒤 병렬 작성 가능하다.
- T016/T017/T018은 각 Red test가 준비된 경우 병렬 가능하다.
- ChatA T025~T028과 ChatB T029~T033은 core Green 이후 병렬 가능하다.
- Portal T034/T035는 병렬 가능하지만 T036/T037보다 먼저 완료한다.
- T039/T041은 전체 기능 Green 이후 독립 실행 가능하고 T043 전에 합류한다.

## Completion Definition

- T001~T043이 모두 완료되고 체크되어야 한다.
- 체크리스트는 evidence link가 있는 항목만 PASS로 전환한다.
- CRITICAL integrity/security failure, 민감정보 노출, K=0 모델 호출, invalid citation clamping, HTTP-only E2E가 하나라도 남으면 완료로 간주하지 않는다.
