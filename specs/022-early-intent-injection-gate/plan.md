# Implementation Plan: 선제적 하이브리드 의도 게이트 및 Llama Prompt Guard 2 (86M)

**Branch**: `022-early-intent-injection-gate` | **Date**: 2026-08-19 | **Spec**: [spec.md](file:///c:/AISERVICE/specs/022-early-intent-injection-gate/spec.md)

## User Review Required

> [!IMPORTANT]
> - **조기 차단(Early Exit)**: 비도메인(코딩, 게임 제작, 수학, 주식, 번역 등) 및 인젝션 질의 발생 시 **DB 커넥션 오픈, 하이브리드 검색, GPU BGE 리랭킹, 4B LLM 추론을 일체 실행하지 않고 20ms 내에 즉시 표준 뷰티 안내를 반환**합니다.
> - **Llama Prompt Guard 2 (86M)**: 순수 로컬 경량 추론(VRAM/RAM 약 300MB, 추론 15ms)으로 외부 API 키 없이 100% 자립 구동됩니다.
> - **참조 리뷰 완전 격리**: 차단된 질의의 경우 UI 하단에 "참조 리뷰 원문" 아코디언이 일체 노출되지 않습니다.

---

## Proposed Changes

Grouped by component layer:

### 1. `bteam/oliview_core` (공통 핵심 가드레일 엔진)

#### [MODIFY] [types.py](file:///c:/AISERVICE/bteam/oliview_core/types.py)
- `GateVerdict`, `EarlyGateDecision`, `SecurityMetricsEvent` 데이터 모델 추가.

#### [MODIFY] [guardrail.py](file:///c:/AISERVICE/bteam/oliview_core/guardrail.py)
- `EarlyIntentGuardrail` 클래스 구현:
  - `sanitize_raw_input()`: NULL 바이트(`\x00`), C0/C1 제어 문자 살균 & 한글 자모 NFC 복원.
  - `_evaluate_tier_1a_rules()`: 비도메인(코딩/게임/수학/번역) 행위 동사 감지 + 위장형 인젝션 차단 + 은유적 뷰티 표현(코딩하느라 주름, 게임오버 피부) 오탐 0% 보장.
  - `_evaluate_tier_1b_prompt_guard()`: `Llama-Prompt-Guard-2-86M` 또는 경량 로컬 분류기 연동, 싱글톤 캐싱, `torch.inference_mode()`, 스레드 락 및 Graceful Fallback.
  - `_mask_pii_for_logging()`: 주민번호, 전화번호, 이메일 마스킹.
  - `evaluate_gate()`: 통합 0ms 캐시/1ms 규칙/15ms 모델 순차 실행 및 EarlyGateDecision 반환.

#### [MODIFY] [pipeline.py](file:///c:/AISERVICE/bteam/oliview_core/pipeline.py)
- `prepare_pipeline_stream()`: Step 0에서 `EarlyIntentGuardrail.evaluate_gate()` 호출, 차단 시 `reference_reviews=[]`, `selected_review_count=0`으로 `_blocked_stream()` 즉시 반환.
- 4B 모델 출력 가드레일 감지 시 이전 토큰 버퍼를 초기화하고 단일 표준 거절 문구로 완전 대체.

---

### 2. `bteam/Oliview_chatbot_b` (Chatbot B FastAPI REST/SSE)

#### [MODIFY] [project_ragapi.py](file:///c:/AISERVICE/bteam/Oliview_chatbot_b/project_ragapi.py)
- `search_products_with_rag()`: `pymysql.connect()` 획득 **이전**에 `EarlyIntentGuardrail.evaluate_gate()` 호출하여 차단 시 DB 커넥션 0개, 검색 0회로 즉시 반환.
- `search_products_with_rag_stream()`: SSE 스트리밍 진입 즉시 `run_in_threadpool`을 통해 게이트 평가, 차단 시 토큰 이벤트 단독 반환 후 조기 종료.
- `generate_llm_rag_answer_stream()`: 버퍼 완전 대체 출력 가드레일 적용.

---

### 3. `bteam/tests/unit` (보안 및 회귀 테스트 스위트)

#### [NEW] [test_early_intent_gate.py](file:///c:/AISERVICE/bteam/tests/unit/test_early_intent_gate.py)
- 비도메인(스네이크 게임, 계산기 등) 15종 조기 차단 테스트 (<20ms).
- 위장형 복합 인젝션 10종 차단 테스트.
- 은유적/부정형/다국어 뷰티 질의 25종 100% 정상 통과 (0% 오탐) 검증.
- 레이턴시 벤치마크 (<20ms).

---

## Verification Plan

### Automated Tests
```bash
python -m unittest tests/unit/test_early_intent_gate.py
```

### Live Container E2E Tests
1. "파이썬으로 스네이크 게임 만들어줘" 질의 시 DB/리랭킹 없이 20ms 내 표준 안내 반환 및 참조 리뷰 아코디언 미노출 확인.
2. "코딩하느라 눈가 주름 생겼는데 아이크림 추천해줘" 질의 시 정상 4B RAG 답변 생성 확인.
3. Chatbot A (`/bteam/chata/`) 및 Chatbot B (`/bteam/chatb/`) 라이브 동작 확인.
