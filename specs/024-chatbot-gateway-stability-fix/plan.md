# Implementation Plan: 챗봇 A/B 런타임 오류 해결 및 vLLM 서빙 게이트웨이 OOM 방어·안정화

**Branch**: `024-chatbot-gateway-stability-fix` | **Date**: 2026-08-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/024-chatbot-gateway-stability-fix/spec.md`

---

## Summary

`bteam/Oliview_chatbot_b/common.py` 및 `bteam/Oliview_chatbot_a/llm_common.py`의 `budget_context_documents()` 내 `is_9b` 미정의 버그를 완전 수정하고, `model_gateway`의 `ProcessManager`에 OOM 서브프로세스 감지 및 즉시 무중단 자동 재생성(Self-Healing) 로직을 추가하며, 챗봇 클라이언트에 503/502 자동 재시도 래퍼를 적용하여 24/7 안정적인 챗봇 서비스를 보장한다.

---

## Technical Context

**Language/Version**: Python 3.12 (uv package manager)
**Primary Dependencies**: `FastAPI`, `Streamlit`, `requests`, `openai` (vLLM client), `llama-cpp-python`
**Target Platform**: Linux Docker containers (`vllm-serv-gateway`, `oliview_chatbot_a`, `oliview_chatbot_b`)
**Performance Goals**: 서브프로세스 크래시 복구 < 3초, 챗봇 질의 성공률 100%, 503 오류 발생률 0.0%
**Constraints**: 기존 프롬프트 가드레일 및 모델 라우팅 로직 100% 호환 유지

---

## Constitution Check

- **Principle 1 (TDD & Verification)**: PASS - 가드레일 함수 및 재시도 로직 단위 테스트 선행 작성
- **Principle 2 (Service Isolation)**: PASS - B팀 챗봇 모듈 및 model_gateway 내에서 격리 수정
- **Principle 3 (Observability & Logging)**: PASS - 프로세스 재기동 및 재시도 이벤트 구조화 로깅
- **Principle 4 (Clear Documentation in Korean)**: PASS - 모든 기술 명세 및 계획 한국어 기술

---

## Project Structure

### Documentation
```text
specs/024-chatbot-gateway-stability-fix/
├── spec.md              # Feature specification
├── plan.md              # Implementation plan (This file)
├── research.md          # Technical research & decisions
├── data-model.md        # Core entities & lifecycle
├── quickstart.md        # Verification run guide
├── contracts/
│   └── stability_contracts.md # Interface & retry contracts
└── checklists/
    └── requirements.md  # Quality checklist
```

### Source Code Touched
```text
bteam/
├── Oliview_chatbot_a/
│   └── llm_common.py           # [MODIFY] is_9b 선언 및 503 자동 재시도 래퍼
├── Oliview_chatbot_b/
│   ├── common.py               # [MODIFY] is_9b 선언
│   └── project_ragapi.py       # [MODIFY] 503 자동 재시도 래퍼
└── tests/
    └── test_chatbot_stability.py # [NEW] is_9b 및 예외 방어 단위 테스트
model_gateway/
└── src/
    └── process_manager.py      # [MODIFY] OOM 서브프로세스 즉각 자동 복구 로직 강화
```

---

## Implementation Phases

### Phase 1: Chatbot A/B Variable Scope & NameError Fix
1. `bteam/Oliview_chatbot_b/common.py`: `budget_context_documents()`에 `is_9b = "9b" in str(model_name).lower()` 선언 추가.
2. `bteam/Oliview_chatbot_a/llm_common.py`: `budget_context_documents()`에 `is_9b = "9b" in str(model_name).lower()` 선언 추가.
3. `bteam/tests/test_chatbot_stability.py`: 단위 테스트 작성 및 통과 검증.

### Phase 2: Gateway Self-Healing & Client-Side Retry
1. `model_gateway/src/process_manager.py`: 서브프로세스 종료 감지 시 즉각 자동 재기동(`ensure_running()`) 로직 강화.
2. `bteam/Oliview_chatbot_a/llm_common.py` & `bteam/Oliview_chatbot_b/project_ragapi.py`: 503/502/ConnectionError 시 1초 간격 2회 자동 재시도 적용.

### Phase 3: Container Rebuild & Live E2E Verification
1. `docker compose build vllm-serv oliview_chatbot_a oliview_chatbot_b` 및 재기동.
2. 챗봇 A 및 챗봇 B에 실제 뷰티 질의 10회 요청하여 200 OK 응답 및 렌더링 무결성 검증.
