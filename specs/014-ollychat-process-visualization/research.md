# Research & Technical Decisions: OllyChat RAG 파이프라인 실시간 시각적 진행과정

**Feature**: `014-ollychat-process-visualization`  
**Date**: 2026-08-19  
**Status**: Completed  

---

## 1. 개요 및 연구 목표

본 연구는 올리챗 A(Streamlit) 및 올리챗 B(FastAPI + Web UI) 환경에서 기존의 단순 정적 로딩/스피너를 최신 생성형 AI 서비스(Perplexity/ChatGPT) 수준의 **실시간 4단계 시각적 진행 인디케이터(Step Progress)**, **실시간 토큰 스트리밍(Token-by-token Streaming)**, **참조 리뷰 아코디언**, **오류 복구 칩/재시도 UX**로 고도화하기 위한 최적의 기술 결정과 아키텍처 패턴을 수립합니다.

---

## 2. 핵심 기술 결정 사항 (Technical Decisions)

### 결정 1: Streamlit(올리챗 A) 실시간 단계 시각화 및 스트리밍 메커니즘
- **Decision**: Streamlit 내장 `st.status()` 컨테이너와 콜백 함수(Callback Protocol) 및 제너레이터(Generator) 패턴 채택.
- **Rationale**:
  - `st.status(label, expanded=True)`는 별도의 프론트엔드 React 컴포넌트 추가 없이도 상태 레이블 변경, 단계별 하위 메시지 동적 추가, 완료 시 `status.update(label="✅ 리뷰 종합 분석 완료...", state="complete", expanded=False)`로 자동 축약되는 완벽한 네이티브 UX를 제공함.
  - LLM 4단계 토큰 생성 시 `st.write_stream()` 제너레이터와 연동하여 첫 토큰 응답 시간(TTFT) 체감을 극대화함.
  - 과거 대화 이력(`st.session_state.messages`) 렌더링 시에는 완료 상태(`state="complete", expanded=False`)의 `st.status` 또는 커스텀 CSS 접이식 뱃지로 즉시 렌더링하여 재실행 부하를 방지함.
- **Alternatives Considered**:
  - `st.empty()` 기반 문자열 덮어쓰기: 이전 단계 로그가 사라지고 축약 아코디언 UI를 별도로 구현해야 하여 복잡도 증가.
  - 커스텀 Streamlit 컴포넌트(React wrapper): 런타임 의존성 증가 및 빌드 오버헤드로 YAGNI 원칙 위배.

### 결정 2: FastAPI / Web UI(올리챗 B) 실시간 진행 이벤트 및 스트리밍 프로토콜
- **Decision**: SSE(Server-Sent Events: `text/event-stream`) 엔드포인트 `/api/v1/search/stream` 신설 및 기존 REST `/api/v1/search` 하위 호환 유지.
- **Rationale**:
  - SSE는 WebSocket에 비해 HTTP/1.1 및 HTTP/2 위에서 단방향 서버 푸시를 구현하기 가장 가볍고 표준적인 웹 기술임 (연결 관리, 프록시 호환성 우수).
  - 단계 전환 이벤트(`event: step`, `data: {"step": "HYBRID_SEARCH", "label": "리뷰 검색 중...", "progress": 50}`)와 LLM 토큰 이벤트(`event: token`, `data: {"token": "이"}`), 최종 완료 이벤트(`event: complete`, `data: {"metadata": {...}}`)를 구조화된 JSON으로 전송 가능함.
  - 기존 동기식 `/api/v1/search` 엔드포인트를 그대로 보존하여 기존 호출처의 비파괴성(NFR-001)을 100% 보장함.
- **Alternatives Considered**:
  - WebSocket: 전이중 통신이 필요 없는 RAG 단방향 파이프라인에서 불필요한 핸드셰이크 및 커넥션 풀 관리 복잡성 발생.
  - 단일 Long-Polling REST: 단계별 실시간 화면 갱신이 불가능하여 Perplexity 스타일의 반응성 제공 불가.

### 결정 3: RAG 백엔드 수명 주기 이벤트 콜백 아키텍처
- **Decision**: `StepCallback` 추상화 및 이벤트 데이터클래스(`PipelineStepEvent`) 정의.
- **Rationale**:
  - `05.chatbot.py`와 `project_ragapi.py` 내부의 핵심 비즈니스 로직(하이브리드 검색, BGE-M3 임베딩, BM25, Cross-Encoder 리랭킹, Qwen LLM 추론)을 전혀 변경하지 않고, 각 단계 진입 및 완료 시점에 `callback.on_step(Phase, metadata)`를 호출하도록 디커플링함.
  - Streamlit 환경에서는 UI 업데이트 콜백(`StreamlitStepCallback`), FastAPI 환경에서는 `asyncio.Queue` 기반 SSE 브로드캐스터로 교체 주입 가능.
- **Alternatives Considered**:
  - 전역 이벤트 버스/RxPY: 단일 질의 단위 수명 주기에 과도한 복잡성(Over-engineering).

### 결정 4: 오류 및 0건 검색 시 복구 UX (Retry & Recommendation Chips)
- **Decision**: 상태 박스 하단에 추천 완화 검색어 칩(`div.rec-chips`)과 '다시 시도(Retry)' 버튼을 즉시 주입하고, 클릭 시 입력창 반영 및 자동 재검색 트리거.
- **Rationale**:
  - 모바일 및 데스크톱 환경에서 사용자가 질문 전체를 다시 타이핑할 필요 없이 단 1번의 탭/클릭으로 완화된 키워드(예: 브랜드명만 분리 검색, 일반 속성 검색)로 재질의할 수 있음.

---

## 3. 의존성 및 호환성 검토

| 기술 / 라이브러리 | 적용 대상 | 버전 / 요구사항 | 호환성 검토 결과 |
|---|---|---|---|
| **Streamlit (`st.status`, `st.write_stream`)** | 올리챗 A (`06.app.py`) | Streamlit >= 1.30.0 | 기존 `bteam/Oliview_chatbot_a` pyproject/uv 환경에서 기본 지원 확인 |
| **FastAPI (`StreamingResponse`)** | 올리챗 B (`project_ragapi.py`) | FastAPI (Starlette SSE) | `spt.responses.StreamingResponse` 표준 지원, 추가 의존성 없음 |
| **BGE-Reranker-v2 & ChromaDB** | 올리챗 A/B 백엔드 | PyTorch / ChromaDB / MySQL | 기존 RAG 및 가드레일 로직 완벽 보존 (NFR-001) |
| **HTML5 EventSource / Fetch Streams** | 올리챗 B (`index.html`) | Vanilla JS | 최신 모바일/데스크톱 브라우저 100% 호환 |

---

## 4. 결론

모든 기술적 모호성과 질문(`NEEDS CLARIFICATION`)이 완전히 해소되었으며, 기존 런타임 환경의 비파괴성을 준수하면서 Streamlit `st.status`와 FastAPI SSE 기반의 실시간 시각화 파이프라인 설계를 확정합니다.
