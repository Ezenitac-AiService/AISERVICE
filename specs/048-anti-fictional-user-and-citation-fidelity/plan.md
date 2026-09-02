# Implementation Plan: 048-anti-fictional-user-and-citation-fidelity

**Branch**: `048-anti-fictional-user-and-citation-fidelity` | **Date**: 2026-09-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/048-anti-fictional-user-and-citation-fidelity/spec.md`

---

## Summary

Qwen 3.5 2B/4B 기반 RAG의 가상 사용자 창작, 근거 없는 직접 인용, 인용 번호 초과, 감성 극성 반전을 해결한다. 방어 체계는 SSOT 프롬프트, `ContextReviewRegistry`, UTF-8/SSE 경계 안전 carry buffer, exact-match 인용 검증, 사후 groundedness sanitizer로 구성한다. 검색 문서는 비신뢰 데이터로 취급하며 prompt injection, PII, XSS, unbounded input을 별도 보안 경계에서 통제한다.

ChatA와 ChatB는 공통 코어를 사용하되 각각 소비자 컨시어지와 분석가 대시보드로 차별화한다. 모바일 UX는 `dvh`/`svh`, `visualViewport`, 키보드·focus·dialog 접근성을 실기기 및 자동 테스트로 검증한다. 성능과 검색 임계값은 고정 수치를 사실로 가정하지 않고 재현 가능한 benchmark 및 평가 코퍼스 결과로 승인한다.

---

## Technical Context

**Language/Version**: Python 3.10+, Vanilla JavaScript ES6+, Modern CSS
**Primary Dependencies**: FastAPI, Uvicorn, LangGraph/LangChain, PyTorch, llama.cpp, 선택적 vLLM, Pydantic v2
**Storage**: MariaDB/MySQL (`v_active_rag_catalog`, `v_rag_reviews`), Redis(session 및 atomic distributed rate/concurrency limit 포함)
**Testing**: `pytest`, `pytest-asyncio`, `pytest-mock`, JSON Schema Draft 2020-12 validator, ChatA/ChatB Playwright 브라우저 회귀, Ruff, Mypy, ESLint, TypeScript `checkJs`, html-validate, Stylelint, Nginx/Compose contract 및 독립 container smoke test
**Target Platform**: Linux Docker Compose 및 Windows Server Nginx Gateway. 포트·URL·healthcheck·운영 한계·SLA는 `contracts/runtime_environment_schema.json`으로 검증한 환경을 공통 SSOT로 사용하고 Pydantic Settings와 Nginx template renderer가 같은 값을 소비
**Hardware Candidates**: GTX 1070은 DEMO llama.cpp만 평가하고, RTX 2080/RTX 3060 단일 노드는 DEMO/PRODUCTION 후보 용량을 비교한다. PRODUCTION 승인은 분산 캐시와 2개 이상 model-serving worker를 갖춘 GPU cluster topology에서 별도로 판정한다
**Project Type**: Multi-service RAG web application and model-serving gateway
**Required Latency Gate**: DEMO zero-search ≤3초 및 일반 RAG ≤20초. 승인된 PRODUCTION cluster의 4-slot workload는 P95 TTFT ≤1.5초, P95 full response ≤8초, aggregate throughput ≥25 tokens/s, OOM 0건이며 worker 1개 장애에서 안전한 기권/재시도 정책을 유지해야 한다
**Integrity Constraints**: `0 <= K <= MAX_SELECTED_REVIEWS <= 20`, 유효 인용 `1 <= N <= K`, `K=0` 모델 무호출, 무효 인용 무보정 제거
**Scale**: 약 57,000개 리뷰와 다중 서브시스템 포털

---

## Constitution Check

*GATE: Phase 3 구현에 진입하기 전에 T001~T018의 계약 및 실패 테스트를 완료하고 Red 결과를 기록한다.*

- [x] **Principle I — Language & Communication**: 사용자 문서와 산출물을 한국어로 유지한다.
- [ ] **Principle II — Test-First & Contract Verification**: T001의 계약·frontend quality config 확정 후 T002~T018 실패 테스트를 먼저 작성하고, ChatA/ChatB browser Red를 포함한 승인 결과 이후 T019부터 구현하며 Phase 3/4 Green gate와 T044 전체 회귀·Python/JavaScript/HTML/CSS 정적 분석을 통과한다.
- [ ] **Principle III — Service Modularity & Isolation**: T005/T026에서 sync 안전성을 검증하고 T047에서 ChatA·ChatB·Model Gateway·Nginx Gateway의 독립 container build/up/health/test와 network isolation을 검증한다.
- [ ] **Principle IV — Observability & Structured Logging**: T004의 실패 테스트 후 T020/T021에서 correlation ID, latency, model invocation, abstention, guardrail 결과와 pre-model/pre-log/pre-render redaction을 구현한다.
- [x] **Principle V — Simplicity & YAGNI**: 고정 token count 대신 금지 패턴 길이에 기반한 단일 carry buffer와 사후 sanitizer를 사용한다.
- [ ] **Principle VI — Integrity**: T008~T018의 평가에서 K=0 무호출, exact quote 후 display redaction, 무효 인용과 결속 claim 제거, polarity fidelity, browser zero-flicker와 UI/API 경계 보안을 확인한다.
- [ ] **Principle VII — Infrastructure SSOT**: T003 실패 테스트 후 T019에서 공통 runtime environment schema, Pydantic consumer, Nginx template renderer, 미해결 변수/임의 기본값/셀프 루프백 차단을 구현한다.

체크되지 않은 항목은 계획상 위반이 아니라 **구현 진입을 차단하는 미완료 게이트**다. 완료 전에는 이 계획을 Constitution PASS로 간주하지 않는다.

---

## Project Structure

### Documentation

```text
specs/048-anti-fictional-user-and-citation-fidelity/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── verification-report.md                 # T048 실행 시 생성
├── contracts/
│   ├── auth_transport_contract.md
│   ├── runtime_environment_schema.json
│   ├── core_prompt_contract.json
│   ├── chat_api_contract.json             # request
│   ├── chat_api_response_contract.json
│   ├── sse_event_contract.json
│   ├── structured_log_contract.json
│   └── changelog_schema.json
├── checklists/requirements.md
└── tasks.md
```

### Source and Test Layout

```text
C:\AISERVICE\
├── quality/frontend/
│   ├── package.json
│   ├── package-lock.json
│   ├── eslint.config.js
│   ├── tsconfig.json                    # allowJs + checkJs
│   ├── .htmlvalidate.json
│   └── stylelint.config.js
├── scripts/render_gateway_config.py
├── bteam/
│   ├── oliview_core/
│   │   ├── config.py
│   │   ├── prompts.py
│   │   ├── guardrail.py
│   │   ├── logging.py
│   │   ├── security.py
│   │   ├── rate_limit.py
│   │   ├── nodes/synthesis_node.py
│   │   ├── utils/document_top_p.py
│   │   └── tests/
│   │       ├── test_anti_hallucination_pipeline.py
│   │       ├── test_stream_boundary_safety.py
│   │       ├── test_prompt_injection_and_redaction.py
│   │       └── test_contracts_and_logging.py
│   ├── Oliview_chatbot_a/
│   │   ├── static/css/style.css
│   │   ├── static/js/chat_ui.js
│   │   └── tests/
│   │       ├── test_concierge_mobile_contract.py
│   │       └── test_concierge_stream_playwright.py
│   ├── Oliview_chatbot_b/
│   │   ├── project_ragapi.py
│   │   ├── index.html
│   │   └── tests/
│   │       ├── test_analyst_dashboard_contract.py
│   │       └── test_analyst_stream_playwright.py
│   └── sync_core.py
├── gateway/html/index.html
├── gateway/html/changelog.html
├── gateway/nginx.conf.template
├── gateway/nginx.conf
├── gateway/tests/test_feature_048_portal_changelog.py
└── tests/test_hardware_concurrency.py
```

---

## Architecture Decisions

### 1. Contract-first and test-first

API request/response, SSE event, structured log, prompt, changelog 계약을 먼저 고정한다. 구현 태스크는 계약 검증 및 실패 테스트의 Red 증거가 기록되기 전에는 시작하지 않는다.

### 2. Grounding pipeline

1. Prompt hardening: 시스템 지시와 비신뢰 검색 문서를 분리한다.
2. Context registry: `K`와 허용 인용 태그를 결정론적으로 계산한다.
3. Stream boundary interceptor: 디코딩된 text chunk를 동적 carry buffer로 검사한다.
4. Final sanitizer: exact quote, citation bounds, 결속 claim, polarity 및 금지 라벨을 검증한다. 민감정보가 있는 exact-match 원문은 동일 정책으로 redaction한 `display_quote`만 외부로 보낸다.
5. Abstention: `K=0`이면 prompt 구성과 모델 호출을 생략한다. 모델 생성 후 검증 실패는 이미 발생한 호출을 숨기지 않고 `model_invoked=true`로 기록한 뒤 생성 결과를 폐기하고 검증된 기권 응답을 반환한다.

### 3. Security boundaries

- query/review는 `security.py`의 prompt injection 및 PII 검사 후 최소 권한 context로 전달하며, 같은 redaction policy를 pre-model, pre-log, pre-render 경계에 적용한다. 인용 exact-match는 서버 내부 원문으로 수행하고 외부 계약에는 `display_quote`와 `quote_redacted`만 노출한다.
- 출력은 plain-text safe sink를 기본으로 하며 허용된 Markdown만 sanitize한다.
- direct API는 설정 기반 Bearer validator를 사용하고 브라우저는 Secure/HttpOnly/SameSite opaque session cookie와 session-bound CSRF token을 사용한다. JavaScript에는 Bearer/session 원문을 노출하지 않는다.
- 인증 결과는 공통 principal로 정규화하고 Redis atomic operation/TTL 기반 principal+service rate 및 concurrency lease를 모든 worker가 공유한다. PRODUCTION Redis 장애는 fail-closed `503`으로 처리한다.
- client timeout/output 요청값은 Settings cap과 `min(client, server)` 규칙으로 결합하고 판별형 response/error 및 SSE event schema를 강제한다.
- 구조화 로그에는 원문 query/review/prompt/token을 저장하지 않는다.

### 4. Configuration and synchronization

`contracts/runtime_environment_schema.json`으로 검증한 환경이 포트·URL·모드·모델 endpoint·검색 후보값·Bearer/session/CSRF·Redis·query/output token·timeout·rate/concurrency 한계·DEMO/PRODUCTION SLA의 유일한 설정 공급원이다. `config.py`는 Python consumer이며 `scripts/render_gateway_config.py`는 같은 환경으로 `gateway/nginx.conf.template`을 렌더링한다. 필수값 누락, 미해결 template 변수, 임의 기본값, 생성된 `nginx.conf` 직접 편집은 fail-closed 처리한다. 외부 vLLM은 기본 비활성화한다. 이 feature에서는 runtime 서비스가 service-local core copy만 import하고 `bteam/oliview_core`는 canonical source로만 사용한다. 같은 프로세스에서 master와 copy를 혼용하지 않는다. `sync_core.py`는 dry-run, hash manifest, 원자적 교체와 충돌 차단 없이는 write mode를 실행하지 않는다. 공유 package migration은 별도 feature로 분리한다.

### 5. Evaluation and performance

- 검색 후보값 `0.85/0.60/0.25`는 평가 대상이지 확정 사실이 아니다.
- 평가 보고서는 retrieval/claim precision·recall, context utilization, abstention rate 및 보안 공격 통과 결과를 기록한다.
- 하드웨어 보고서는 모델 해시, quant, context pool, slot, prompt/output 길이, GPU/driver, server version과 반복 횟수를 포함한다.
- llama.cpp의 context pool은 slot 전체가 공유하므로 “64K 4-slot”을 슬롯당 64K로 표현하지 않는다.
- 단일 GPU 결과는 PRODUCTION 승인 근거로 대체하지 않는다. PRODUCTION 보고서는 분산 캐시 종류/일관성 정책, worker 수, routing/failover, worker 1개 장애 결과를 추가로 기록하며 topology 미확보 시 `NOT VERIFIED`로 판정한다.

---

## Implementation Phases

### Phase 1 — Governance, contracts and reproducible baselines

- Draft 2020-12 계약을 확정하고 schema 자체의 valid/invalid fixture는 Green baseline으로 검증하며, 미구현 runtime adapter conformance만 Red로 기록한다.
- 현재 테스트 수는 T002에서 `pytest --collect-only`로 산출하여 baseline으로 기록한다.
- 평가 코퍼스와 hardware benchmark workload를 구현 전에 고정한다.

### Phase 2 — Red tests

- ChatA/ChatB/core에 hallucination, exact quote, citation bounds, K=0, polarity, stream split 테스트를 작성한다.
- prompt injection, PII, XSS, 공통 env→Pydantic/Nginx rendering, direct Bearer와 browser session/CSRF, Redis atomic distributed limit/fail-closed, API cap, 판별형 response, logging redaction, sync safety 테스트를 작성하고 실패를 확인한다.
- ChatA persona/mobile/accessibility/구조화 link card/browser DOM zero-flicker, ChatB browser DOM zero-flicker/adaptive dashboard/실제 pipeline-stage event/score visualization, portal/changelog canonical route/schema/filter/navigation/accessibility의 실패 테스트를 구체적 파일에 작성한다.

### Phase 3 — Core Green implementation

- 공통 runtime environment validator와 Nginx renderer, 운영 한계/SLA를 포함한 Pydantic consumer, structured logging, browser/direct auth, Redis atomic limiter, pre-model/pre-log/pre-render security policy, prompt registry, sanitizer, stream interceptor, retrieval gate를 구현한다.
- 무효 인용은 다른 인용 번호로 clamping하지 않고 결속 claim과 함께 제거한 뒤 claim-evidence를 재검증한다.
- sync safety gate를 통과한 뒤에만 ChatA/ChatB 코어를 동기화한다.
- core 계약·무결성·보안·로깅·sync 테스트가 Green인 증거를 기록한 뒤 Phase 4로 이동한다.

### Phase 4 — ChatA and ChatB applications

- ChatA는 endpoint-bound concierge persona, browser session/CSRF, 구조화된 허용 도메인 link event와 mobile-first UX를 적용한다.
- ChatB는 endpoint-bound analyst persona, browser session/CSRF, document threshold controls, 실제 `pipeline_stage` event 기반 4-stage timeline과 adaptive dashboard를 적용한다.
- 모든 동적 콘텐츠는 안전한 sink와 접근 가능한 상호작용을 사용한다.
- ChatA/ChatB별 API·SSE 계약 테스트를 Green으로 확인한 뒤 Phase 6으로 진행한다.

### Phase 5 — Portal and changelog

- 포털 카드와 changelog를 구현하고 `gateway/nginx.conf.template`에 canonical `/changelog` 규칙을 추가한 뒤 공통 환경 renderer로 `gateway/nginx.conf`를 생성한다. `all`은 UI 필터 상태로만 사용한다.
- keyboard, focus, dialog, status message, 48px target 및 responsive breakpoints를 검증한다.

### Phase 6 — Final evaluation and live verification

- 검색 threshold calibration을 먼저 수행하고 승인값을 설정 문서에 반영한다.
- calibration 이후 core, ChatA, ChatB와 portal의 수집된 전체 테스트, Ruff/Mypy 및 lockfile 기반 ESLint/TypeScript `checkJs`/html-validate/Stylelint를 실행한다.
- 고정 평가·보안 코퍼스, DEMO 단일 노드 benchmark 및 분산 캐시/GPU cluster PRODUCTION benchmark를 구분해 수행한다.
- ChatA·ChatB·Model Gateway·Nginx Gateway의 독립 container build/up/health/test와 network isolation을 검증하고, 환경변수 `BASE_URL`의 HTTPS endpoint에서 Playwright DOM zero-flicker·모바일·canonical route E2E를 수행한 뒤 결과를 `verification-report.md`에 기록한다.

---

## Release Gates

1. 계약과 Red 테스트 증거 없이는 구현을 시작하지 않는다.
2. CRITICAL integrity/security test 실패가 하나라도 있으면 E2E로 진행하지 않는다.
3. core·ChatA·ChatB·gateway 수집 테스트, feature Python touchpoint Ruff/Mypy 및 JavaScript·HTML·CSS touchpoint ESLint/TypeScript `checkJs`/html-validate/Stylelint가 모두 통과해야 한다.
4. 로그와 응답의 민감정보 노출 건수가 0이어야 한다.
5. DEMO latency 상한을 충족해야 하며, PRODUCTION은 분산 캐시·GPU cluster gate를 통과하지 않으면 승인하지 않는다.
6. 각 서비스가 독립 container build/up/health/test 및 network isolation 검증을 통과해야 한다.
7. checklist는 증거 파일과 검증 명령이 연결된 항목만 PASS 처리한다.
