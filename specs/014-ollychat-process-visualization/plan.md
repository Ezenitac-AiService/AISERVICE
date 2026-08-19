# Implementation Plan: OllyChat RAG 파이프라인 실시간 시각적 진행과정

**Branch**: `014-ollychat-process-visualization` | **Date**: 2026-08-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/014-ollychat-process-visualization/spec.md`

---

## Summary

올리브영 화장품 리뷰 분석 챗봇인 **올리챗(OllyChat A: Streamlit, OllyChat B: FastAPI Web UI)**의 기존 단순 정적 로딩/스피너 방식을 개선하여, **실시간 4단계 RAG 파이프라인 진행 상태(질문 의도 분석 ➡️ 하이브리드 검색 ➡️ 리랭킹 ➡️ LLM 심층 생성)를 시각적으로 노출(Step Progress / Status Cards)**하고, 완료 시 **자동 축약 뱃지(소요시간/참조리뷰수 요약)** 및 **참조 리뷰 원문 아코디언**, **토큰 단위 타이핑 스트리밍**, **에러 복구 칩/재시도 UX**를 구현합니다.

---

## Technical Context

**Language/Version**: Python 3.10+, HTML5 / Vanilla JavaScript (ES6+)  
**Primary Dependencies**: Streamlit (>=1.30.0), FastAPI, Uvicorn, httpx, PyMySQL, NumPy, ChromaDB, BGE-M3, BGE-Reranker-v2, OpenAI Client (vLLM 호환)  
**Storage**: ChromaDB (벡터 임베딩), MySQL (`review_aspect_sentences`, `brands` 테이블)  
**Testing**: pytest (단위 및 통합 테스트, FastAPI TestClient 기반 SSE 계약 테스트)  
**Target Platform**: Linux Server / Docker Container / Modern Web Browsers (Chrome, Safari, Edge, Mobile Responsive)  
**Project Type**: Web Application & AI Chatbot Serving (Streamlit UI + FastAPI Backend & Web Client)  
**Performance Goals**:
- 상태 표시 렌더링 부가 오버헤드: 총 50ms 미만 (FR-008)
- 질문 전송 후 1단계 상태 표시: 0.2초 이내 (SC-001)
- 4단계 실시간 토큰 스트리밍 적용으로 체감 첫 토큰 응답 시간(TTFT) 최소화  
**Constraints**:
- 기존 `05.chatbot.py` 및 `project_ragapi.py`의 검색/리랭킹 정확도 및 2B/4B 라우팅 로직 100% 무결성 보존 (NFR-001)
- 올리브영 브랜드 테마 컬러(`--olive-green: #2f9e44`) 및 가독성 최적화 디자인 준수 (NFR-002)  
**Scale/Scope**: B팀 올리챗 A(`06.app.py`, `05.chatbot.py`), B팀 올원챗 B(`index.html`, `project_ragapi.py`), 2개 서브시스템

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **I. 언어 및 커뮤니케이션 정책**: 모든 사용자 대상 설명, 문서, 계획서, 주석, 질문/답변을 한국어로 작성함 (통과)
- [x] **II. TDD 및 테스트 우선주의**: 단계별 콜백 프로토콜 및 SSE 스트리밍 엔드포인트에 대해 단위/계약 테스트를 선행 정의함 (통과)
- [x] **III. 서비스 모듈화 및 격리**: `bteam/Oliview_chatbot_a`와 `bteam/Oliview_chatbot_b`의 독립적 실행 및 비파괴적 무결성을 보존함 (통과)
- [x] **IV. 관측 가능성 및 구조화된 로깅**: 단계별 지연 시간(Latency), 처리 건수, 모델명을 구조화된 이벤트 메타데이터로 기록함 (통과)
- [x] **V. 단순성 및 점진적 진화 (YAGNI)**: 복잡한 메시지 큐 대신 경량 Callback Protocol 및 표준 SSE(Server-Sent Events)를 채택하여 불필요한 복잡도를 제거함 (통과)

---

## Project Structure

### Documentation (this feature)

```text
specs/014-ollychat-process-visualization/
├── spec.md              # 요구사항 명세서 (/speckit-specify, /speckit-clarify)
├── plan.md              # 본 구현 계획서 (/speckit-plan)
├── research.md          # 기술 결정 및 프로토콜 조사 보고서 (Phase 0)
├── data-model.md        # 데이터 모델 및 스키마 명세서 (Phase 1)
├── quickstart.md        # 검증 가이드 및 실행 절차 (Phase 1)
├── contracts/           # 인터페이스 계약 (Phase 1)
│   ├── callback_protocol.md  # Python Callback Protocol 명세
│   ├── sse_stream_api.md     # SSE 스트리밍 엔드포인트 규격
│   └── ui_contract.md        # UI/CSS 컴포넌트 구조 계약
└── checklists/
    └── requirements.md  # 명세 품질 체크리스트
```

### Source Code (repository structure)

```text
bteam/
├── Oliview_chatbot_a/
│   ├── 05.chatbot.py          # [MODIFY] RAG 단계별 Callback 연동 및 제너레이터 지원
│   ├── 06.app.py              # [MODIFY] st.status 실시간 진행 박스, 스트리밍, 아코디언, 복구 칩 적용
│   └── common/
│       └── step_callback.py   # [NEW] 공통 StepCallbackProtocol 및 이벤트 데이터클래스 정의
│
├── Oliview_chatbot_b/
│   ├── project_ragapi.py      # [MODIFY] /api/v1/search/stream SSE 엔드포인트 추가
│   ├── index.html             # [MODIFY] 4단계 타임라인 인디케이터, SSE 수신, 아코디언, 복구 칩 적용
│   └── common.py              # [MODIFY] 단계별 이벤트 래퍼 유틸리티
│
└── tests/
    ├── test_step_callback_a.py  # [NEW] 올리챗 A 콜백 및 이벤트 전이 단위 테스트
    └── test_sse_stream_b.py     # [NEW] 올리챗 B SSE 스트림 엔드포인트 계약 테스트
```

**Structure Decision**: 
B팀 내의 독립된 두 서비스(Streamlit 기반 올리챗 A와 FastAPI/웹 기반 올리챗 B)의 파일 구조를 그대로 유지하며, 각 서브프로젝트의 독립성을 해치지 않도록 서비스별 모듈을 확장하는 구조를 채택했습니다.

---

## Complexity Tracking

> **Constitution Check 위반 사항 없음 (No violations)**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| 없음 (None) | N/A | N/A |
