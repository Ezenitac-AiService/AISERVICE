# Phase 1: API & Interface Contracts (Feature 046)

**Feature**: [spec.md](../spec.md) (Oliview ChatA FastAPI 웹 서비스 완전 전환 및 Uvicorn 단일 엔트리포인트 일원화)

---

## 1. Web & API Endpoints

### 1.1 Root Web UI (`GET /`)
- **Description**: 데스크탑/모바일 반응형 Vanilla Web 메인 페이지 서빙
- **Request**: `GET /`
- **Response**: `200 OK` (`text/html`)
  - `static/index.html` 본문 반환

---

### 1.2 Health Check (`GET /health`)
- **Description**: 컨테이너 오케스트레이션 및 게이트웨이 헬스 체크
- **Request**: `GET /health`
- **Response**: `200 OK` (`application/json`)
  ```json
  {
    "status": "ok",
    "app": "Oliview ChatA FastAPI",
    "version": "2.0.0"
  }
  ```

---

### 1.3 Real-Time Chat SSE Stream (`POST /api/v1/chat/stream`)
- **Description**: 실시간 4단계 파이프라인 상태 알림 및 LLM 답변 토큰 SSE 스트리밍
- **Request**: `POST /api/v1/chat/stream`
  - **Headers**: `Content-Type: application/json`
  - **Body**:
    ```json
    {
      "query": "식물나라 토너 자극성 및 수분감 알려줘",
      "session_id": "sess_20260902_abc123",
      "category_hint": "스킨케어",
      "tenant_id": "chata"
    }
    ```
- **Response**: `200 OK` (`text/event-stream`)
  - **Stream Frame Examples**:
    ```text
    event: step_update
    data: {"event_type": "step_update", "step_id": "INTENT", "step_name": "🔍 1. 의도 분석 및 라인명 매칭", "status": "running", "trace_id": "tr_123"}

    event: step_update
    data: {"event_type": "step_update", "step_id": "SEARCH", "step_name": "📚 2. ChromaDB 하이브리드 리뷰 검색", "status": "running", "trace_id": "tr_123"}

    event: step_update
    data: {"event_type": "step_update", "step_id": "RERANK", "step_name": "⚡ 3. BGE 리랭커 정밀 순위화", "status": "running", "trace_id": "tr_123"}

    event: step_update
    data: {"event_type": "step_update", "step_id": "LLM", "step_name": "💬 4. 객관적 리뷰 심층 분석 답변 생성", "status": "running", "trace_id": "tr_123"}

    event: token_chunk
    data: {"event_type": "token_chunk", "content": "식물나라", "trace_id": "tr_123"}

    event: token_chunk
    data: {"event_type": "token_chunk", "content": " 토너는", "trace_id": "tr_123"}

    event: final_result
    data: {"event_type": "final_result", "metadata": {"total_latency_sec": 2.1, "selected_review_count": 5, "reference_reviews": [...]}, "trace_id": "tr_123"}
    ```

---

### 1.4 Session History Retrieval (`GET /api/v1/chat/history/{session_id}`)
- **Description**: Redis 세션 저장소로부터 대화 이력 조회 (새로고침 복원용)
- **Request**: `GET /api/v1/chat/history/{session_id}`
- **Response**: `200 OK` (`application/json`)
  ```json
  {
    "session_id": "sess_20260902_abc123",
    "messages": [
      {
        "role": "user",
        "content": "식물나라 토너 자극성 및 수분감 알려줘",
        "timestamp": 1788336700.0,
        "metadata": null
      },
      {
        "role": "assistant",
        "content": "### 🌿 식물나라 토너 분석 결과...",
        "timestamp": 1788336702.5,
        "metadata": {
          "total_latency_sec": 2.5,
          "selected_review_count": 5
        }
      }
    ],
    "total_count": 2
  }
  ```

---

## 2. Static Assets Contract

- `/static/css/style.css`: 데스크탑 2열 레이아웃, 모바일 3x2 카테고리 그리드, Safe-Area 인셋, 다크/라이트 테마
- `/static/js/app.js`: SSE EventSource / Fetch 스트림 리더, 1클릭 질문 예시 바인딩, 세션 복원, 아코디언 토글
