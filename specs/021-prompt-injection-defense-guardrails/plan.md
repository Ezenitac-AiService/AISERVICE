# Implementation Plan: Oliview Chatbot A/B 다계층 프롬프트 인젝션 방어 가드레일

**Branch**: `021-prompt-injection-defense-guardrails` | **Date**: 2026-08-19 | **Spec**: [spec.md](file:///c:/AISERVICE/specs/021-prompt-injection-defense-guardrails/spec.md)

**Input**: Feature specification from `/specs/021-prompt-injection-defense-guardrails/spec.md`

## Summary

2026년 8월 기준 최신 LLM 보안 표준(OWASP Top 10 for LLM 2025/2026)에 맞춰, 올리브영 챗봇 A/B 공통 코어(`bteam/oliview_core`)에 4계층 다층 방어(Defense-in-Depth) 프롬프트 인젝션 가드레일 모듈(`guardrail.py`)을 구축합니다. 이 모듈은 제로너비/유니코드 난독화 해제, ReDoS 안전 시그니처 필터, XML 프롬프트 샌드박싱, RAG 수동 데이터 격리 및 카나리아 토큰 출력 검증을 통해 지연시간 오버헤드 10ms 이하로 직접/간접 인젝션 및 시스템 프롬프트 유출을 100% 방어합니다.

## Technical Context

**Language/Version**: Python 3.12, Standard `re`, `unicodedata`, `uuid`, `time`, `logging`

**Primary Dependencies**: `pydantic>=2.7.0`, `bteam.oliview_core`

**Storage**: Memory / In-Memory Pattern Cache

**Testing**: Python `unittest` (Direct Injection Vectors, Jailbreak Vectors, False Positive Tests, Latency Benchmark)

**Target Platform**: Linux Docker Containers (`oliview_chatbot_a`, `oliview_chatbot_b`) & Windows Dev Env

**Project Type**: Python Core Library (`bteam/oliview_core`) & Web/API Integration

**Performance Goals**: 가드레일 추가 지연시간 <10ms, 정상 질의 오탐률 0%, 인젝션 차단율 100%

**Constraints**: 서브모듈 격리 유지, 비파괴적 점진적 통합, ReDoS 방어

**Scale/Scope**: `bteam/oliview_core/guardrail.py`, `bteam/oliview_core/pipeline.py`, `bteam/Oliview_chatbot_b/project_ragapi.py`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. 언어 및 커뮤니케이션 정책**: 모든 산출물, 인터페이스, 주석 및 사용자 거절 안내 한국어 작성 준수 (PASS)
- **II. TDD 및 계약 검증**: `guardrail_contracts.md` 정의 및 20종 공격 벡터 + 20종 정상 질문 단위 테스트 선행 (PASS)
- **III. 서비스 모듈화 및 격리**: `bteam/oliview_core` 공통 모듈에 한정 구축하여 Chatbot A/B가 동일 코드를 공유하도록 설계 (PASS)
- **IV. 관측 가능성 및 로깅**: 차단 이벤트에 대한 JSON 포맷 구조화 보안 로깅 적용 (PASS)
- **V. 단순성 및 YAGNI**: 무거운 외부 보안 프레임워크 대신 초경량 고성능 Python 네이티브 알고리즘 채택 (PASS)

## Project Structure

### Documentation (this feature)

```text
specs/021-prompt-injection-defense-guardrails/
├── spec.md              # Feature specification
├── plan.md              # Implementation plan
├── research.md          # Technical research and decisions
├── data-model.md        # Security entities and lifecycle model
├── quickstart.md        # Verification and benchmark guide
├── contracts/
│   └── guardrail_contracts.md # Interface contracts
└── tasks.md             # Tasks list (generated in next phase)
```

### Source Code Layout

```text
bteam/
├── oliview_core/
│   ├── guardrail.py     # [NEW] Multi-tier prompt injection defense engine
│   └── pipeline.py      # [MODIFY] Integrate guardrail in RAG orchestrator
├── Oliview_chatbot_b/
│   └── project_ragapi.py # [MODIFY] Integrate guardrail in FastAPI endpoints
└── tests/
    └── unit/
        └── test_guardrail.py # [NEW] Comprehensive security & benchmark test suite
```

**Structure Decision**: 공통 로직을 `bteam/oliview_core/guardrail.py`에 싱글톤/클래스메소드 구조로 배치하여 Chatbot A(Streamlit)와 Chatbot B(FastAPI)가 동일한 보안 방어선을 공유하도록 설계합니다.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
| :--- | :--- | :--- |
| 없음 (None) | N/A | 표준 Python 네이티브 정규화 및 정규식 알고리즘 기반 초경량 설계 채택 |
