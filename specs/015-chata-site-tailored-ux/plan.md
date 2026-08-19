# Implementation Plan: 통합 3대 챗봇(올리챗 A, 올원챗 B, PILOS) 사이트 맞춤형 RAG 프로세스 시각화 및 인터랙션 고도화

**Branch**: `015-unified-chatbots-tailored-ux` | **Date**: 2026-08-19 | **Spec**: [spec.md](./spec.md)

---

## Summary

본 계획은 AISERVICE 생태계의 3대 챗봇(**올리챗 A, 올원챗 B, A-Team PILOS**)에 각각 최적화된 **4단계 실시간 프로세스 시각화, 지연 없는 실시간 토큰 스트리밍, 1클릭 대화형 추천 칩(단일 큐 세션 방어), 외부 원본/공식몰(올리브영, 네이버금융/DART) 정밀 연동, XSS 보안 방어**를 사이트별 특성에 맞게 완결형으로 구현하기 위한 아키텍처 및 구현 로드맵을 정의합니다.

---

## Technical Context

**Language/Version**: Python 3.12 (uv, virtualenv)  
**Primary Dependencies**: 
- **B-Team (ChatA & ChatB)**: Streamlit (`st.status`, `st.write_stream`, `st.expander`), FastAPI (`StreamingResponse`), httpx, Pydantic v2, pymysql, ChromaDB, BM25, BGE-M3, BGE-Reranker
- **A-Team (PILOS)**: FastAPI, Jinja2, httpx, Pydantic v2, PyMySQL, pandas, scikit-learn
**Storage**: MySQL (`oliview_project`, `pilos_db`), ChromaDB Vector Store  
**Testing**: pytest / standalone automated test suites (`tests/test_chata_stream.py`, `tests/test_chatb_noise_filter.py`, `tests/test_pilos_stream.py`, `tests/test_xss_escape.py`, `tests/test_cross_chatbot_latency.py`)  
**Target Platform**: Linux Docker Containers (`oliview_chatbot_a:8501`, `oliview_chatbot_b:8002`, `pilos_web:8000`, `aiservice-gateway:8080`)  
**Project Type**: Multi-Service Fullstack Web & AI Chatbots  
**Performance Goals**: UI 및 콜백 지연 시간 오버헤드 < 50ms, 첫 토큰 출력 시간(TTFT) < 1.5s  
**Constraints**: 비파괴적 무결성 보존(기존 모델 서빙 및 DB 스키마 유지), XSS 100% 방어, 세션 레이스 컨디션 0건  
**Scale/Scope**: 3개 대화형 AI 서비스, 5개 테스트 모듈  

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **Principle I (Language & Communication)**: 모든 명세서, 계획서, 코드 주석, 사용자 응답은 한국어로 작성됨.
- [x] **Principle II (TDD & Contract Verification)**: 단위/계약/통합/성능 테스트 코드를 우선 구축하고 검증함.
- [x] **Principle III (Service Modularity & Isolation)**: A-Team과 B-Team의 가상환경과 컨테이너 격리를 보존함.
- [x] **Principle IV (Observability & Logging)**: 4단계 진행 상태 및 지연 시간을 구조화된 이벤트로 기록 및 모니터링함.
- [x] **Principle V (YAGNI & Simplicity)**: 사이트별 프레임워크(Streamlit, Vanilla JS, Jinja2)에 가장 직관적이고 가벼운 구현을 채택함.

---

## Project Structure

### Documentation (this feature)

```text
specs/015-chata-site-tailored-ux/
├── spec.md              # 통합 3대 챗봇 기능 명세서
├── plan.md              # 본 구현 계획서 (/speckit-plan)
├── research.md          # 4대 기술 의사결정 기록 (Phase 0)
├── data-model.md        # 데이터 모델 및 DTO 정의 (Phase 1)
├── quickstart.md        # 테스트 및 검증 가이드 (Phase 1)
├── contracts/           # 서비스별 인터페이스 계약 스키마 (Phase 1)
│   ├── chata_callback_contract.json
│   ├── chatb_sse_contract.json
│   └── pilos_sse_contract.json
├── checklists/
│   └── requirements.md  # 16개 항목 품질 검증 체크리스트
└── tasks.md             # 구현 작업 목록 (/speckit-tasks 대상)
```

### Source Code Mapping

```text
# 1. B-Team: 올리챗 A (Streamlit)
bteam/Oliview_chatbot_a/
├── 05.chatbot.py              # 하이브리드 RAG 파이프라인 + 스트림 생성기
├── 06.app.py                  # st.status 4단계 시각화, pending_query 큐, 올리브영 정제 링크
└── common/
    └── step_callback.py       # StepCallbackProtocol, clean_product_name_for_search

# 2. B-Team: 올원챗 B (FastAPI + Web UI)
bteam/Oliview_chatbot_b/
├── project_ragapi.py          # /api/v1/search/stream SSE 엔드포인트 + clean_product_name
├── index.html                 # escapeHtml() XSS 방어, 4단계 타임라인, 복구 칩
└── common.py                  # 데이터 모델, 유틸리티 함수

# 3. A-Team: PILOS 챗봇 (금융 감성지수)
ateam/pilos-sentiment-index/pilos/
├── service/
│   └── chatbot_service.py     # 4단계 금융 분석 콜백 라이프사이클 + 스트림 생성기
├── web/
│   ├── app.py                 # /api/v1/chat/stream SSE 엔드포인트
│   └── templates/
│       └── index.html         # CHAT_BLOCK 원클릭 칩 + 네이버증권/DART 공시 링크

# 4. Automated Tests
tests/
├── test_chata_stream.py           # 올리챗 A 4단계 콜백 및 세션 큐 테스트
├── test_chatb_noise_filter.py     # 올원챗 B 상품명 노이즈 정제 및 XSS 테스트
├── test_pilos_stream.py           # PILOS 4단계 금융 타임라인 및 SSE 계약 테스트
├── test_xss_escape.py             # 3대 챗봇 XSS/HTML 인젝션 방어 테스트
└── test_cross_chatbot_latency.py  # 3대 챗봇 오버헤드 레이턴시 벤치마크 (<50ms)
```

---

## Phased Implementation Plan

### Phase 1: 올리챗 A (Streamlit) UX 및 인터랙션 고도화
1. `bteam/Oliview_chatbot_a/common/step_callback.py`에 `clean_product_name_for_search()` 및 `urllib.parse.quote_plus` 헬퍼 함수 추가.
2. `06.app.py`에 `st.session_state.pending_query` 단일 진입 큐 패턴 적용하여 상단 질문 예시, 카테고리 속성 칩, 하단 복구 칩 클릭 시 이중 실행 없는 1클릭 즉시 질의 실행 구현.
3. `06.app.py`의 `st.expander` 참조 리뷰 카드 내에 정제된 `올리브영 상세보기 ↗` 새 탭 버튼 및 `html.escape` 보안 처리.

### Phase 2: 올원챗 B (FastAPI / Web) 백포팅 및 안정화
1. `bteam/Oliview_chatbot_b/project_ragapi.py` 및 `common.py`에 `clean_product_name_for_search()` 적용.
2. `bteam/Oliview_chatbot_b/index.html`에 `escapeHtml()` XSS 방어 유틸리티를 장착하고 올리브영 정밀 링크 생성 로직 고도화.
3. 복구 칩 및 카테고리 템플릿 클릭 시 즉시 스트리밍 검색 실행 연동.

### Phase 3: A-Team PILOS 챗봇 4단계 시각화 및 SSE 스트리밍
1. `ateam/pilos-sentiment-index/pilos/service/chatbot_service.py`에 4단계 금융 분석 프로세스 콜백(`IDENTIFY_STOCK` ➡️ `SUPPLY_DEMAND_METRIC` ➡️ `NEWS_SENTIMENT_VERIFICATION` ➡️ `LLM_REPORT_SYNTHESIS`) 및 토큰 제너레이터 구현.
2. `ateam/pilos-sentiment-index/pilos/web/app.py`에 `/api/v1/chat/stream` SSE 라우트 추가.
3. PILOS 웹 템플릿에 `CHAT_BLOCK_DEFINITIONS` 1클릭 추천 칩 및 네이버 증권/DART 공시 바로가기 링크 컴포넌트 추가.

### Phase 4: 통합 테스트 및 실서비스 검증
1. 5개 자동화 테스트 스위트 작성 및 실행 (`tests/test_chata_stream.py` 등).
2. Docker 컨테이너 재시작 및 Nginx 게이트웨이(8080 포트) 실서비스 E2E 통신 검증.
