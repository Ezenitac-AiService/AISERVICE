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
**Storage**: MariaDB/MySQL (`v_active_rag_catalog`, `v_rag_reviews`), Redis
**Testing**: `pytest`, `pytest-asyncio`, `pytest-mock`, JSON Schema Draft 2020-12 validator, 브라우저 접근성/XSS 회귀 도구
**Target Platform**: Linux Docker Compose 및 Windows Server Nginx Gateway. 포트·URL·healthcheck는 `bteam/oliview_core/config.py`의 환경변수 기반 SSOT만 사용
**Hardware Candidates**: GTX 1070은 llama.cpp만 평가, RTX 2080/RTX 3060은 Linux에서 llama.cpp와 vLLM을 동일 workload로 비교
**Project Type**: Multi-service RAG web application and model-serving gateway
**Required Latency Gate**: DEMO 모드 zero-search ≤3초, 일반 RAG ≤20초. TTFT ≤1.5초, full stream ≤8초, 4-slot ≥25 tokens/s는 benchmark 승인 전 목표치
**Integrity Constraints**: `0 <= K <= MAX_SELECTED_REVIEWS <= 20`, 유효 인용 `1 <= N <= K`, `K=0` 모델 무호출, 무효 인용 무보정 제거
**Scale**: 약 57,000개 리뷰와 다중 서브시스템 포털

---

## Constitution Check

*GATE: Phase 3 구현에 진입하기 전에 T001~T015의 계약 및 실패 테스트를 완료하고 Red 결과를 기록한다.*

- [x] **Principle I — Language & Communication**: 사용자 문서와 산출물을 한국어로 유지한다.
- [ ] **Principle II — Test-First & Contract Verification**: T001의 계약 확정 후 T002~T015 실패 테스트를 먼저 작성하고, 승인된 Red 결과 이후 T016부터 구현한다.
- [ ] **Principle III — Service Modularity & Isolation**: T005/T022에서 sync dry-run, hash 검증, 원자적 교체, 예상치 못한 대상 변경 차단을 검증한다.
- [ ] **Principle IV — Observability & Structured Logging**: T004의 실패 테스트 후 T017에서 correlation ID, latency, model invocation, abstention, guardrail 결과와 PII 마스킹을 구현한다.
- [x] **Principle V — Simplicity & YAGNI**: 고정 token count 대신 금지 패턴 길이에 기반한 단일 carry buffer와 사후 sanitizer를 사용한다.
- [ ] **Principle VI — Integrity**: T008~T014의 평가에서 K=0 무호출, exact quote, 무효 인용 제거, polarity fidelity를 확인한다.
- [ ] **Principle VII — Infrastructure SSOT**: T003 실패 테스트 후 T016에서 환경변수, 외부 vLLM opt-in, 셀프 루프백 차단을 구현한다.

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
├── verification-report.md                 # T043 실행 시 생성
├── contracts/
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
├── bteam/
│   ├── oliview_core/
│   │   ├── config.py
│   │   ├── prompts.py
│   │   ├── guardrail.py
│   │   ├── logging.py
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
│   ├── Oliview_chatbot_b/
│   │   ├── project_ragapi.py
│   │   ├── index.html
│   │   └── tests/
│   └── sync_core.py
├── gateway/html/index.html
├── gateway/html/changelog.html
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
4. Final sanitizer: exact quote, citation bounds, polarity 및 금지 라벨을 검증한다.
5. Abstention: `K=0` 또는 검증 실패 시 모델 호출을 생략하거나 검증된 기권 응답을 반환한다.

### 3. Security boundaries

- query/review는 prompt injection 및 PII 검사 후 최소 권한 context로 전달한다.
- 출력은 plain-text safe sink를 기본으로 하며 허용된 Markdown만 sanitize한다.
- API는 인증, rate limit, 입력·출력 상한, timeout, 오류 및 SSE event schema를 강제한다.
- 구조화 로그에는 원문 query/review/prompt/token을 저장하지 않는다.

### 4. Configuration and synchronization

`config.py`가 포트·URL·모드·모델 endpoint·검색 후보값의 유일한 설정 공급원이다. 외부 vLLM은 기본 비활성화한다. `sync_core.py`는 임시 호환 전략이며 dry-run, hash manifest, 원자적 교체와 충돌 차단 없이는 write mode를 실행하지 않는다.

### 5. Evaluation and performance

- 검색 후보값 `0.85/0.60/0.25`는 평가 대상이지 확정 사실이 아니다.
- 평가 보고서는 retrieval/claim precision·recall, context utilization, abstention rate 및 보안 공격 통과 결과를 기록한다.
- 하드웨어 보고서는 모델 해시, quant, context pool, slot, prompt/output 길이, GPU/driver, server version과 반복 횟수를 포함한다.
- llama.cpp의 context pool은 slot 전체가 공유하므로 “64K 4-slot”을 슬롯당 64K로 표현하지 않는다.

---

## Implementation Phases

### Phase 1 — Governance, contracts and reproducible baselines

- Draft 2020-12 계약을 확정하고 schema validation을 실패 우선으로 구축한다.
- 현재 테스트 수는 `pytest --collect-only`로 산출하여 baseline으로 기록한다.
- 평가 코퍼스와 hardware benchmark workload를 구현 전에 고정한다.

### Phase 2 — Red tests

- ChatA/ChatB/core에 hallucination, exact quote, citation bounds, K=0, polarity, stream split 테스트를 작성한다.
- prompt injection, PII, XSS, API bounds, logging redaction, sync safety 테스트를 작성하고 실패를 확인한다.

### Phase 3 — Core Green implementation

- config SSOT, structured logging, prompt registry, sanitizer, stream interceptor, retrieval gate를 구현한다.
- 무효 인용은 제거하며 다른 인용 번호로 clamping하지 않는다.
- sync safety gate를 통과한 뒤에만 ChatA/ChatB 코어를 동기화한다.

### Phase 4 — ChatA and ChatB applications

- ChatA에 concierge persona와 mobile-first UX를 적용한다.
- ChatB에 analyst persona, document threshold controls, adaptive dashboard를 적용한다.
- 모든 동적 콘텐츠는 안전한 sink와 접근 가능한 상호작용을 사용한다.

### Phase 5 — Portal and changelog

- 포털 카드와 changelog를 구현하고 `all`은 UI 필터 상태로만 사용한다.
- keyboard, focus, dialog, status message, 48px target 및 responsive breakpoints를 검증한다.

### Phase 6 — Final evaluation and live verification

- core, ChatA, ChatB의 수집된 전체 테스트를 실행한다.
- 고정 평가·보안 코퍼스, 검색 threshold calibration, hardware benchmark를 수행한다.
- 환경변수 `BASE_URL`의 HTTPS endpoint에서 E2E를 수행하고 결과를 `verification-report.md`에 기록한다.

---

## Release Gates

1. 계약과 Red 테스트 증거 없이는 구현을 시작하지 않는다.
2. CRITICAL integrity/security test 실패가 하나라도 있으면 E2E로 진행하지 않는다.
3. core·ChatA·ChatB 수집 테스트가 모두 통과해야 한다.
4. 로그와 응답의 민감정보 노출 건수가 0이어야 한다.
5. DEMO latency 상한과 하드웨어 OOM 기준을 충족해야 한다.
6. checklist는 증거 파일과 검증 명령이 연결된 항목만 PASS 처리한다.
