# Phase 0: Research & Technical Decisions (Feature 046)

**Feature**: [spec.md](./spec.md) (Oliview ChatA FastAPI 웹 서비스 완전 전환 및 Uvicorn 단일 엔트리포인트 일원화)

---

## 1. Research Topics & Technical Decisions

### 1.1 FastAPI Web Service & SSE Streaming Architecture
- **Decision**: `bteam/Oliview_chatbot_a/main.py`를 단일 웹 진입점으로 확정하고, `FastAPI`의 `StreamingResponse(media_type="text/event-stream")`를 통해 Server-Sent Events(SSE) 스트리밍 제공.
- **Rationale**:
  - Streamlit의 전체 Re-run 패러다임에서 벗어나 진정한 실시간 비동기 토큰 스트리밍 구현.
  - `MultiTargetGraphOrchestrator`와 직접 연동하여 4단계 파이프라인 상태(의도 분석 → RAG 검색 → BGE 리랭킹 → 토큰 생성)를 클라이언트에 실시간 푸시.
  - 프로세스 메모리 누수 및 모듈 캐싱 충돌(`NameError: name 'httpx' is not defined` 등)을 구조적으로 방지.
- **Alternatives Considered**:
  - *Streamlit 유지 및 CSS 래핑*: 스트리밍 중단 인터랙션 불가, 메모리 점유율 높음, 모듈 핫 리로드 불안정으로 기각.
  - *WebSocket 도입*: 단순 단방향 토큰 스트리밍에는 SSE가 HTTP/2 및 Nginx 프록시 친화적이며 오버헤드가 적어 SSE 선택.

### 1.2 Desktop Pixel-Identical & 2026 Mobile Responsive Design System
- **Decision**: Vanilla HTML5 + CSS3 + ES6 JavaScript를 활용하여 빌드 단계 없이 0.5초 이내 고속 로드되는 반응형 웹 UI 구축.
- **Rationale**:
  - **데스크탑 ($\ge 768\text{px}$)**: 기존 Streamlit ChatA의 시각적 요소(상단 2열 설정/예시 박스, 브랜드 칩, 카테고리 버튼, 하단 고정 입력바)를 100% 동일한 레이아웃과 색상 팔레트(`#2E9E44`, `#F8F9FA`)로 재현하여 사용자 경험 연속성 보장.
  - **모바일 ($\le 768\text{px}$)**: 3x2 카테고리 컴팩트 그리드, Safe-Area 인셋(`env(safe-area-inset-top)` / `env(safe-area-inset-bottom)`), 참조 리뷰 바텀 시트 드로어 적용.
- **Alternatives Considered**:
  - *React/Vue SPA 도입*: 별도의 Node.js 빌드 체인과 번들링이 필요하며 컨테이너 용량이 비대해져 단일 정적 서빙(Vanilla Web) 선택.

### 1.3 Redis Session Store & Refresh History Restoration
- **Decision**: 브라우저 `sessionStorage`에 `session_id`를 보관하고, `GET /api/v1/chat/history/{session_id}` 엔드포인트를 통해 `RedisSessionStore`의 이전 대화 내역을 조회/복원.
- **Rationale**:
  - 브라우저 새로고침이나 모바일 화면 전환 시에도 대화 맥락이 온전히 유지됨.
  - 전사 공통 모듈인 `bteam/oliview_core/session.py`를 단일 진실 공급원(SSOT)으로 재사용.
- **Alternatives Considered**:
  - *클라이언트 로컬스토리지 단독 보관*: 서버 측 세션 관리 및 다중 디바이스/컨테이너 로그 추적과의 정합성이 깨지므로 기각.

### 1.4 Dockerfile Entrypoint & Legacy Quarantine
- **Decision**:
  - `bteam/Oliview_chatbot_a/Dockerfile`의 `CMD`를 `["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8501"]`로 변경.
  - `bteam/Oliview_chatbot_a/app.py`를 `bteam/Oliview_chatbot_a/legacy_archive/06.03.app.py`로 격리 이동.
  - 모든 상대 경로를 `static/...`, `api/v1/...`로 통일하여 Nginx 프록시 서브패스(`https://ezenitac.duckdns.org/bteam/chata/`)와 로컬 직접 접근(`http://localhost:8501/`) 동시 지원.
- **Rationale**:
  - 컨테이너 및 로컬 개발 환경 전반에서 Streamlit 호출 경로를 영구 차단하여 프레임워크 파편화 종결.
