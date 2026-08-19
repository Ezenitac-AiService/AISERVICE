# Phase 1: Security Entities & Guardrail Data Model

**Feature**: `021-prompt-injection-defense-guardrails`

## Overview

본 피처는 프롬프트 인젝션 탐지 및 방어 파이프라인에서 사용되는 보안 이벤트 데이터 구조 및 가드레일 상태 모델을 정의합니다.

---

## 1. Guardrail Entities

### A. `InjectionDetectionResult`
- `is_blocked`: `bool` — 인젝션 또는 위험 패턴 탐지 여부 (True: 차단, False: 안전)
- `risk_level`: `str` — 위험 수준 (`"NONE"`, `"LOW"`, `"MEDIUM"`, `"HIGH"`, `"CRITICAL"`)
- `matched_rule`: `Optional[str]` — 매칭된 보안 규칙명 (예: `"JAILBREAK_DAN"`, `"PROMPT_LEAK_REQUEST"`, `"INSTRUCTION_OVERRIDE"`, `"TAG_ESCAPE_ATTEMPT"`)
- `sanitized_text`: `str` — 제로너비 문자 및 유사문자가 정규화된 텍스트
- `execution_time_ms`: `float` — 가드레일 검사 소요 시간(ms)
- `reason`: `Optional[str]` — 보안 탐지 상세 사유 (내부 로그용)

### B. `SecurityEventLog`
- `timestamp`: `float` — 이벤트 발생 Unix Timestamp
- `event_id`: `str` — UUID 고유 이벤트 식별자
- `client_ip`: `Optional[str]` — 요청 클라이언트 IP
- `session_id`: `Optional[str]` — 대화 세션 식별자
- `user_query`: `str` — 사용자 원본 입력 (마스킹 적용)
- `matched_rule`: `str` — 탐지된 규칙
- `risk_level`: `str` — 위험 등급
- `action_taken`: `str` — 조치 내용 (`"BLOCKED_SAFE_RESPONSE"`, `"OUTPUT_MASKED"`)

### C. `SandboxedPromptPayload`
- `system_prompt`: `str` — 카나리아 토큰 및 보안 지침이 포함된 시스템 프롬프트
- `user_content`: `str` — XML 태그로 샌드박싱된 사용자 질의 및 참조 컨텍스트
- `canary_token`: `str` — 출력 유출 감지용 32자리 무작위 카나리아 토큰

---

## 2. Guardrail Pipeline Lifecycle

```text
[User Input: "query"]
         │
         ▼
[Step 1: De-obfuscation] ──▶ Remove Zero-width, Normalize Unicode
         │
         ▼
[Step 2: Signature Filter] ──▶ Regex Threat Patterns & Context Checking
         │
         ├── [If Threat Detected] ──▶ Log Security Event ──▶ Return SAFE_BLOCKED_RESPONSE (End)
         │
         ▼ [If Safe]
[Step 3: XML Sandboxing] ──▶ Wrap with <user_query> & Escaped Tags + Instruction Defense
         │
         ▼
[Step 4: LLM Generation] ──▶ Streaming Token Generation with Canary Token Guard
         │
         ▼
[Step 5: Output Guardrail] ──▶ If Canary Leaked ──▶ Mask Output Stream
         │
         ▼
[Final Safe Response to User]
```
