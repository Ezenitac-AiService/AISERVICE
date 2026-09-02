# Phase 1: Data Model (Feature 046)

**Feature**: [spec.md](./spec.md) (Oliview ChatA FastAPI 웹 서비스 완전 전환 및 Uvicorn 단일 엔트리포인트 일원화)

---

## 1. Data Entities & Schemas

### 1.1 ChatStreamRequest (클라이언트 질의 요청)
클라이언트가 `/api/v1/chat/stream`으로 전송하는 JSON 페이로드:

```python
class ChatStreamRequest(BaseModel):
    query: str = Field(..., description="사용자 질문 (예: 차앤박 프로폴리스 앰플 수분감 어때?)")
    session_id: Optional[str] = Field(default=None, description="고유 세션 식별자 (생략 시 신규 생성)")
    category_hint: Optional[str] = Field(default=None, description="사용자가 선택한 카테고리 힌트 (예: 스킨케어, 선케어 등)")
    tenant_id: str = Field(default="chata", description="서비스 테넌트 식별자")
```

### 1.2 ChatStreamEvent (SSE 스트리밍 이벤트)
백엔드가 클라이언트로 푸시하는 표준 Server-Sent Events 구조:

```python
class ChatStreamEvent(BaseModel):
    event_type: str = Field(..., description="이벤트 타입: step_update, token_chunk, final_result, error")
    step_id: Optional[str] = Field(default=None, description="현재 단계 ID (INTENT, SEARCH, RERANK, LLM)")
    step_name: Optional[str] = Field(default=None, description="UI 표시용 단계명 (예: 🔍 의도 분석 중...)")
    status: Optional[str] = Field(default=None, description="상태: running, complete, error")
    content: Optional[str] = Field(default=None, description="생성된 텍스트 토큰 청크")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="지연 시간, 참조 리뷰 목록 등 메타데이터")
    error_message: Optional[str] = Field(default=None, description="오류 발생 시 에러 메시지")
    trace_id: str = Field(..., description="분산 추적 Trace ID")
```

### 1.3 SessionHistoryResponse (대화 이력 복원 응답)
`GET /api/v1/chat/history/{session_id}` 응답 데이터:

```python
class SessionMessage(BaseModel):
    role: str = Field(..., description="user 또는 assistant")
    content: str = Field(..., description="메시지 본문")
    timestamp: float = Field(..., description="메시지 생성 타임스탬프")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="참조 리뷰 및 실행 메타데이터")

class SessionHistoryResponse(BaseModel):
    session_id: str = Field(..., description="세션 식별자")
    messages: List[SessionMessage] = Field(default_factory=list, description="대화 메시지 목록")
    total_count: int = Field(..., description="총 메시지 건수")
```

---

## 2. Redis Key Structure (단일 진실 공급원)

- **Session History Key**: `oliview:session:{session_id}:history` (Type: List, TTL: 24시간)
- **Session Meta Key**: `oliview:session:{session_id}:meta` (Type: Hash, TTL: 24시간)
- **L2 Embedding Cache**: `oliview:l2:emb:{hash}` (Type: String, TTL: 7일)
- **L3 Reranking Cache**: `oliview:l3:rerank:{hash}` (Type: String, TTL: 24시간)
