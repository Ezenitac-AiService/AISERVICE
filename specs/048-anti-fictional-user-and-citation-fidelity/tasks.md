# Implementation Tasks: 048-anti-fictional-user-and-citation-fidelity

**Feature Branch**: `048-anti-fictional-user-and-citation-fidelity`
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)
**Status**: Blocked until Phase 1 contracts and Phase 2 Red tests are approved

---

## Execution Rules

- Phase 3 이후 구현 태스크는 T001~T018의 계약·fixture·실패 테스트가 완료되고 Red 결과가 기록되기 전에는 시작하지 않는다. 계약 schema 자체의 valid/invalid fixture는 Green baseline으로 기록하고, 아직 연결되지 않은 runtime conformance만 Red 증거로 사용한다.
- 무효 인용은 다른 유효 번호로 clamping하거나 근거를 재지정하지 않고 결속 factual claim과 함께 제거한 뒤 claim-evidence 관계를 재검증한다.
- `StreamingTokenInterceptor`는 호환 이름이며 UTF-8 decoded text chunk와 동적 carry buffer를 처리한다. 고정 token window를 사용하지 않는다.
- `document_score_threshold=0.85`, second score `0.60`, cliff `0.25`는 T043에서 승인할 초기 후보값이며 public schema나 runtime의 무조건 기본값으로 사용하지 않는다.
- runtime은 service-local core copy만 import하고 `bteam/oliview_core`는 canonical source로 사용한다. 같은 프로세스에서 master/copy를 혼용하지 않는다.
- `sync_core.py` write mode는 dry-run, hash manifest, 원자적 교체, 충돌 차단 테스트가 Green인 경우에만 실행한다.
- ChatA/ChatB persona는 server `ServiceIdentity`로 고정하고 client payload의 persona 필드는 거부한다.
- 브라우저에는 Bearer/session 원문을 노출하지 않으며 session/CSRF를 principal로 정규화한다. 모든 worker의 rate/concurrency 상태는 Redis atomic operation으로 공유한다.
- `gateway/nginx.conf`는 공통 환경 schema와 template renderer로만 생성하며 직접 편집하지 않는다.

---

## Phase 1: Governance, Contracts & Baselines

**Purpose**: 계약 우선주의와 재현 가능한 평가 기준을 구현 전에 확정한다.

- [x] T001 `contracts/auth_transport_contract.md`, `contracts/runtime_environment_schema.json`, `contracts/core_prompt_contract.json`, `contracts/chat_api_contract.json`, `contracts/chat_api_response_contract.json`, `contracts/sse_event_contract.json`, `contracts/structured_log_contract.json`, `contracts/changelog_schema.json`을 검토·승인하고 `quality/frontend/`에 lockfile 기반 ESLint/TypeScript `checkJs`/html-validate/Stylelint 설정과 `lint:js`, `typecheck:js`, `lint:html`, `lint:css` scripts를 생성·고정한다 (FR-003, FR-004, FR-018~FR-023, SC-008).
- [x] T002 [P] `bteam/oliview_core/tests/test_contracts_and_logging.py`에 모든 JSON 계약의 schema 자체 valid/invalid fixture, response의 answered/abstained/error 판별 조건, `product_link`/`pipeline_stage` event 및 auth transport fixture가 Green임을 기록하고, runtime adapter conformance는 구현 미연결 Red로 분리한다. `pytest --collect-only -q` 결과도 구현 전 baseline으로 보존한다 (FR-009, FR-013, FR-021, FR-022).
- [x] T003 [P] `bteam/oliview_core/tests/test_config_ssot.py`에 `contracts/runtime_environment_schema.json` 기준 포트·URL·운영 모드·검색값·Bearer/session/CSRF·Redis·query/output token·timeout·principal rate/service concurrency·DEMO/PRODUCTION SLA 필수성 및 무하드코딩 테스트를 작성한다. `config.py`와 `gateway/nginx.conf.template` renderer가 같은 fixture를 소비하고 미해결 변수·생성 산출물 drift·endpoint 누락·셀프 루프백·포트 충돌을 fail-closed하는 Red를 기록한다 (FR-021, FR-023, Constitution VII).
- [x] T004 [P] `bteam/oliview_core/tests/test_structured_logging.py`에 correlation ID, latency, model invocation, abstention, guardrail 필드와 query/review/token/secret 비기록·마스킹 테스트를 작성하고 Red를 기록한다 (FR-019, FR-022, SC-010).
- [x] T005 [P] `bteam/oliview_core/tests/test_sync_core_safety.py`에 dry-run, source/destination hash, 예상치 못한 변경 거부, 원자적 교체 실패 복구 테스트를 작성하고 Red를 기록한다 (Constitution III).
- [x] T006 `bteam/oliview_core/tests/fixtures/feature_048_eval_cases.json`에 정상·희소·부정·혼합·중복·K=0·prompt injection·PII·XSS·Unicode/SSE split·unsafe product URL·pipeline stage 실패·Bearer/session/CSRF·Redis limiter 장애 평가 케이스와 고정 seed를 정의한다 (SC-001~SC-005, SC-009).
- [x] T007 `tests/hardware_workloads/feature_048.json`에 모델 hash, quant, context pool, slot, prompt/output 길이, concurrency, 반복 횟수, GPU/driver/server version, cache 종류/일관성 정책, model-serving worker 수, routing/failover 및 worker 장애 시나리오 기록 형식을 정의한다 (SC-011, Constitution VI).

**Checkpoint**: 계약과 baseline만 확정된 상태이며 구현은 시작하지 않는다.

---

## Phase 2: Failing Tests (Red Gate)

**Purpose**: 모든 core·API·UI·portal 기능과 보안 경계를 실패 테스트로 먼저 고정한다.

- [x] T008 [P][US1] `bteam/Oliview_chatbot_a/tests/test_anti_hallucination_a.py`에 가상 라벨, 원문 불일치 직접 인용, 객관 요약 대체 테스트를 작성하고 Red를 확인한다 (FR-002, FR-003, SC-001).
- [x] T009 [P][US1] `bteam/Oliview_chatbot_b/tests/test_anti_hallucination_b.py`에 동일 방어와 레거시 IT prompt 비노출 테스트를 작성하고 Red를 확인한다 (FR-002, FR-010, SC-001, SC-005).
- [x] T010 [P][US1] `bteam/oliview_core/tests/test_exact_quote_fidelity.py`에 NFC 및 CRLF/CR→LF만 허용하고 공백·구두점·호환문자를 변경하지 않는 서버 내부 substring exact-match, 민감정보 없는 원문 `display_quote`, PII 포함 원문의 redacted `display_quote`/`quote_redacted=true`, 안전한 redaction 불가 시 인용 생략 테스트를 작성한다 (FR-003, FR-019).
- [x] T011 [P][US2] `bteam/oliview_core/tests/test_citation_bounds_and_abstention.py`에 `K=0/1/Kmax`, `N<1`, `N>K`, malformed citation, 결속 factual claim 동반 제거, 제거 후 claim-evidence 재검증, 무보정 및 K=0 model no-call 테스트를 작성한다 (FR-004, FR-007, SC-003, SC-005).
- [x] T012 [P][US2] `bteam/Oliview_chatbot_b/tests/test_polarity_fidelity_b.py`에 polarity inversion 0건, claim-evidence precision 1.00, context utilization 0.90 기준의 긍정·부정·혼합 fixture 테스트를 작성한다 (FR-005, SC-004).
- [x] T013 [P][US3] `bteam/oliview_core/tests/test_stream_boundary_safety.py`에 금지 문자열의 모든 문자 경계, 대표 SSE event 경계, invalid UTF-8, finalize, reconnect 테스트를 작성한다 (FR-006, SC-002).
- [x] T014 [P] `bteam/oliview_core/tests/test_prompt_injection_and_redaction.py`에 직접·간접·다국어·난독화 injection과 pre-model/pre-log/pre-render PII·credential redaction 테스트를 작성한다 (FR-018, FR-019, SC-009).
- [x] T015 [P][US4] `bteam/Oliview_chatbot_a/tests/test_concierge_mobile_contract.py`와 `tests/test_concierge_stream_playwright.py`에 endpoint-bound CONCIERGE, client persona 거부, browser session/CSRF, K=0 response, 360/375/390/414/768/1024px layout, `visualViewport`, keyboard/focus/dialog/status, 48px target, 구조화 `product_link`/허용 host 카드, unsafe URL 비활성화, safe sink/reconnect 및 `MutationObserver` 기준 금지 문자열·검증 전 partial DOM 삽입 0건의 Red 테스트를 작성한다 (FR-008, FR-009, FR-017, FR-020, FR-021, SC-002, SC-006).
- [x] T016 [P][US4] `bteam/Oliview_chatbot_b/tests/test_analyst_dashboard_contract.py`와 `tests/test_analyst_stream_playwright.py`에 endpoint-bound ANALYST, client persona 거부, legacy prompt absence, browser session/CSRF, mobile/tablet/desktop layout, 실제 `pipeline_stage` status/latency timeline, score controls/bars, brand filter, safe rendering 및 `MutationObserver` 기준 금지 문자열·검증 전 partial DOM 삽입 0건의 Red 테스트를 작성한다 (FR-010~FR-013, FR-020, FR-021, SC-002, SC-005, SC-006).
- [x] T017 [P][US5] `gateway/tests/test_feature_048_portal_changelog.py`에 portal cards, canonical `/changelog`와 정적 `changelog.html` 제공, 7 milestones, 8 filter states, schema validation, navigation, keyboard/focus/status, 48px target와 XSS 테스트를 작성한다 (FR-014~FR-017, FR-020, SC-007, SC-009).
- [x] T018 [P] `bteam/oliview_core/tests/test_api_limits_and_sse.py`에 direct Bearer 누락/오류 `401`, Secure/HttpOnly/SameSite session cookie, CSRF 실패 `403`, browser storage secret 0건, principal/service Redis atomic rate key·TTL·concurrency lease, PRODUCTION Redis 장애 `503`, `effective=min(client, server_cap)`, 판별형 answered/abstained/error response, `product_link`/`pipeline_stage` SSE payload, sequence/reconnect와 unsafe URL 테스트를 작성한다 (FR-009, FR-013, FR-020, FR-021, FR-023, SC-009).

**Checkpoint**: T002~T005 및 T008~T018의 예상 실패를 기록하고 사용자 승인을 받은 경우에만 Phase 3으로 진행한다.

---

## Phase 3: Core Green Implementation

**Purpose**: 승인된 Red 테스트를 최소 구현으로 Green 전환한다.

- [x] T019 `contracts/runtime_environment_schema.json` 검증기를 구현하고 `bteam/oliview_core/config.py`를 동일 환경의 Pydantic consumer로 전환한다. `gateway/nginx.conf.template`과 `scripts/render_gateway_config.py`를 추가해 같은 환경으로 `gateway/nginx.conf`를 생성하고 필수값 누락, 미해결 변수, 산출물 drift, 임의 기본값, external vLLM 비명시 활성화 및 self-loopback을 fail-closed 처리한다 (T003, FR-021, FR-023, Constitution VII).
- [x] T020 `bteam/oliview_core/logging.py`에 structured logs, correlation ID, latency/model/abstention/guardrail events와 raw sensitive data prohibition을 구현한다 (T004, FR-019, FR-022).
- [x] T021 `bteam/oliview_core/security.py`에 prompt injection input/output policy, direct Bearer/browser session/CSRF principal normalization과 동일 PII/credential policy의 pre-model, pre-log, pre-render redaction, 서버 내부 exact-match 후 `display_quote` 생성 및 block/abstain 결과를 구현한다. `bteam/oliview_core/rate_limit.py`에는 Redis Lua 또는 동등 atomic operation, TTL, concurrency lease와 PRODUCTION fail-closed를 구현한다 (T010, T014, T018, FR-003, FR-018, FR-019, FR-021).
- [x] T022 `bteam/oliview_core/prompts.py`에 공통 integrity rules, untrusted context delimiter와 server `ServiceIdentity`로만 선택되는 `PersonaType.CONCIERGE/ANALYST` adapters를 구현하고 client persona override를 거부한다 (T008, T009, T014, T015, T016, FR-001, FR-002, FR-010, FR-018).
- [x] T023 `bteam/oliview_core/guardrail.py`에 fictional label 제거, exact quote 검증, invalid citation과 결속 factual claim 동반 제거, 제거 후 polarity/claim-evidence 재검증 및 failure abstention을 구현한다. Citation clamping은 금지한다 (T010~T012, FR-003~FR-005).
- [x] T024 `bteam/oliview_core/nodes/synthesis_node.py`에 UTF-8 decoded chunk 및 forbidden-pattern prefix 기반 carry buffer를 구현하고 final sanitizer/security policy를 결합한다 (T013, T014, FR-006, FR-018, FR-019).
- [x] T025 `bteam/oliview_core/utils/document_top_p.py`에 config-based threshold/cliff candidates, `0 <= K <= configured max <= 20`, K=0 model no-call abstention을 구현한다 (T011, FR-007, FR-012).
- [x] T026 `bteam/sync_core.py`에 dry-run, hash manifest, allowlisted destinations, atomic replacement와 conflict rejection을 구현하여 T005를 Green으로 전환한다.
- [x] T027 T019~T025가 Green인 뒤 `bteam/oliview_core/__init__.py`에 prompt/security/auth/rate-limit, `ProductLinkCard`, `PipelineStageEvent` public API를 export하고 service-local copy가 canonical source와 동일 API를 사용하도록 구성한다. Runtime master import는 추가하지 않는다 (FR-001, FR-009, FR-013, FR-021).
- [x] T028 T019~T027 및 T005가 Green인 상태에서 `bteam/sync_core.py --dry-run`을 검토한 뒤 write sync를 한 번 실행하고 source/destination hash와 service-local import isolation을 기록한다. 이어 core 계약·config·logging·integrity·security·stream·sync 테스트 전체가 Green임을 확인하고 증거를 보존한다.

**Checkpoint**: core contract, integrity, security, logging, sync tests Green.

---

## Phase 4: User Story 1~4 Application Integration

### ChatA — Concierge and Mobile-first

- [x] T029 [US1][US4] ChatA entrypoint에 client override가 불가능한 endpoint-bound `PersonaType.CONCIERGE`, shared security policy, K=0 abstention response를 연결한다 (T008, T015, T022, FR-008, FR-018, FR-019).
- [x] T030 [US4] ChatA API에 direct Bearer와 Secure/HttpOnly/SameSite session/CSRF principal flow, Redis atomic principal/service rate 및 concurrency lease, `min(client, server_cap)` timeout/output limit와 판별형 response/error/SSE contracts를 연결한다 (T018, T019, T021, FR-021, FR-023).
- [x] T031 [P][US4] `bteam/Oliview_chatbot_a/static/css/style.css`에 `100dvh`, `85svh`, 48px target, visible/non-obscured focus와 responsive matrix를 구현한다 (T015, FR-009, FR-017).
- [x] T032 [P][US4] `bteam/Oliview_chatbot_a/static/js/chat_ui.js`에 `visualViewport`, accessible dialog/status, `display_quote`/`quote_redacted`, 구조화 `product_link` event와 `host_validated=true` 링크 카드, safe sink/allowlist sanitizer, pre-render redaction, CSRF header와 reconnect 중 unverified partial discard를 구현한다. Bearer/session 원문을 JavaScript 저장소에 기록하지 않는다 (T010, T014, T015, T018, FR-003, FR-009, FR-019~FR-021).
- [x] T033 [US1][US4] `test_anti_hallucination_a.py`, `test_concierge_mobile_contract.py`, `test_concierge_stream_playwright.py` 및 T018의 ChatA API/SSE subset을 Green으로 전환하고 증거를 기록한다.

### ChatB — Analyst and Adaptive Dashboard

- [x] T034 [US3] `bteam/Oliview_chatbot_b/common.py`와 prompt builder에서 `NO_THINK_SYSTEM_PROMPT`를 제거하고 client override가 불가능한 endpoint-bound `PersonaType.ANALYST`를 연결한다 (T009, T016, T022, FR-010).
- [x] T035 [US3] `bteam/Oliview_chatbot_b/project_ragapi.py`의 streaming prompt builder를 심볼 기준으로 교체하고 shared security/request/판별형 response/SSE contracts와 실제 `pipeline_stage` status/latency 및 구조화 `product_link` event를 적용한다 (T014, T016, T018, FR-009, FR-010, FR-013, FR-018~FR-021).
- [x] T036 [US4] ChatB API와 `/api/brands`에 direct Bearer와 Secure/HttpOnly/SameSite session/CSRF principal flow, Redis atomic principal/service rate 및 concurrency lease, `min(client, server_cap)` timeout/output limit와 safe errors를 적용한다 (T018, T019, T021, FR-021, FR-023).
- [x] T037 [P][US4] `bteam/Oliview_chatbot_b/index.html`에 `document_score_threshold`, `cliff_delta`, max reviews, 실제 `pipeline_stage` event 기반 검색·재정렬·근거 검증·답변 합성 timeline, score bars, mobile/tablet/desktop layout, `display_quote` redaction 상태, CSRF header와 safe DOM을 구현한다. Bearer/session 원문을 JavaScript 저장소에 기록하지 않는다 (T010, T014, T016, T018, FR-003, FR-011~FR-013, FR-019~FR-021).
- [x] T038 [US3][US4] `test_anti_hallucination_b.py`, `test_analyst_dashboard_contract.py`, `test_analyst_stream_playwright.py` 및 T018의 ChatB API/SSE subset을 Green으로 전환하고 ChatB DOM zero-flicker 증거를 기록한다.

---

## Phase 5: User Story 5 Portal & Changelog

- [x] T039 [P][US5] `gateway/html/index.html`의 ChatA/ChatB descriptions와 canonical `/changelog`를 가리키는 Engineering Evolution 2x1 hero card를 구현한다 (T017, FR-014, FR-015).
- [x] T040 [P][US5] `gateway/html/changelog.html`에 `chat_a`, `chat_b`, `model_gateway`, `nginx_gateway`, `oliview_web`, `core`, `pilos` 7 milestones와 `all` UI filter를 구현하고 `gateway/nginx.conf.template`에 exact `/changelog` 정적 제공 및 `/changelog.html` canonical redirect 정책을 추가한다. T019 renderer로 `gateway/nginx.conf`를 재생성하고 drift가 없음을 확인한다 (T003, T017, T019, FR-015, FR-016, FR-023, SC-007).
- [x] T041 [US5] 두 페이지의 dynamic strings를 safe sink로 렌더링하고 keyboard, focus, DOM order, dialog/status semantics, 48px target를 구현한다 (T017, FR-017, FR-020).
- [x] T042 [US5] `gateway/tests/test_feature_048_portal_changelog.py`를 Green으로 전환한다 (SC-007, SC-009).

---

## Phase 6: Calibration, Regression, Performance & Live Verification

- [x] T043 T006 corpus로 `document_score_threshold=0.85`, second score `0.60`, cliff `0.25` 후보를 retrieval/claim precision·recall, groundedness, context utilization, abstention trade-off로 calibration하고 승인값을 Settings/config documentation에 반영한다. Public schema에는 calibration 후보를 `default`로 고정하지 않는다 (FR-007, FR-012, FR-023).
- [x] T044 calibration 반영 후 `pytest --collect-only -q`로 baseline을 갱신하고 core, ChatA, ChatB, gateway tests 전체를 실행하여 collected tests 100% PASS를 확인한다. Python touchpoint에 Ruff/Mypy를 실행하고, `npm --prefix quality/frontend ci` 후 lockfile 기반 `lint:js`, `typecheck:js`, `lint:html`, `lint:css` scripts로 ChatA/ChatB/gateway JavaScript·HTML·CSS touchpoint를 검사하여 모두 exit code 0인 증거를 보존한다 (SC-008, Constitution 품질 게이트).
- [x] T045 T006 corpus를 반복 실행하여 fictional labels, quote mismatch, invalid citations, polarity inversion, prompt injection, PII/XSS와 SC-004 thresholds 결과를 기록한다 (SC-001~SC-005, SC-009).
- [x] T046 `tests/test_hardware_concurrency.py`와 T007 workload로 GTX 1070 llama.cpp 및 RTX 2080/3060 single-node candidates를 DEMO/용량 결과로 측정한다. PRODUCTION은 분산 캐시와 2개 이상 model-serving worker GPU cluster에서 동일 workload, routing/failover 및 worker 1개 장애를 측정해 SC-011을 판정하며 topology 미확보 시 `NOT VERIFIED`로 기록하고 승인하지 않는다.
- [x] T047 ChatA·ChatB·Model Gateway·Nginx Gateway를 각각 독립 container로 build/up/health/test하고 network isolation 및 Compose/Nginx contract를 검증한다. 이어 환경변수 `BASE_URL`의 HTTPS endpoint에서 Playwright `MutationObserver` zero-flicker, ChatA/ChatB, canonical `/changelog`, HTTP→HTTPS, auth failure, rate limit, SSE reconnect, 360/375/390/414/768/1024px device matrix와 승인된 실제 카카오톡 인앱 브라우저 점검을 수행한다 (SC-002, SC-006, SC-007, FR-021, FR-023, Constitution III).
- [x] T048 `specs/048-anti-fictional-user-and-citation-fidelity/verification-report.md`에 contracts, Red/Green evidence, collected test count, Ruff/Mypy 결과, container isolation, calibration, integrity/security metrics, DEMO 단일 노드와 PRODUCTION cluster 결과 또는 `NOT VERIFIED`, unresolved risks를 기록한다.

---

## Dependencies & Execution Order

```text
Phase 1: Contracts & Baselines (T001~T007)
                 |
                 v
Phase 2: Failing Tests / RED (T008~T018)
                 |
                 v  USER APPROVAL GATE
Phase 3: Core GREEN (T019~T028)
                 |
                 +--------------------+
                 v                    v
Phase 4: ChatA/ChatB (T029~T038)   Phase 5: Portal (T039~T042)
                 +--------------------+
                                      v
Phase 6: Calibration & Verification (T043~T048)
```

## Parallel Execution Opportunities

- T002~T007은 T001 contract approval 이후 병렬 가능하다.
- T008~T018은 fixtures와 contracts가 고정된 뒤 병렬 작성 가능하다.
- T019/T020/T021/T022는 대응 Red tests가 준비된 경우 병렬 가능하지만 T027은 T019~T025 Green 이후에만 수행한다.
- ChatA T029~T033과 ChatB T034~T038은 core Green 이후 병렬 가능하다.
- Portal T039/T040은 병렬 가능하지만 T041/T042보다 먼저 완료한다.
- T045/T046은 T044 Green 이후 독립 실행 가능하고 T047은 두 결과와 서비스별 Green gate를 확인한 뒤 수행하며 T048 전에 합류한다.

## Completion Definition

- T001~T048이 모두 완료되고 체크되어야 한다.
- checklist는 evidence link가 있는 항목만 PASS로 전환한다.
- CRITICAL integrity/security failure, sensitive-data exposure, K=0 model call, invalid citation 또는 결속 claim 잔존/clamping, HTTP-only E2E, Python/frontend 정적 분석 실패, Nginx render drift, container isolation 실패가 하나라도 남으면 완료로 간주하지 않는다. PRODUCTION cluster가 없거나 SLA를 통과하지 못한 경우 PRODUCTION은 `NOT VERIFIED`/미승인으로 명시하며 단일 GPU 결과로 대체하지 않는다.
