# API Contract: PILOS 챗봇 실시간 스트리밍 & 캐시 인터페이스

## 1. 개요
본 계약은 PILOS 챗봇의 고정 질문 블록 및 동적 LLM 분석 질의를 처리하는 SSE(`text/event-stream`) 및 REST API 엔드포인트의 통신 명세를 정의합니다.

- **기본 엔드포인트**: `POST /api/chat`
- **고정 종목 엔드포인트**: `POST /api/stocks/{stock_code}/chat`

---

## 2. 요청 명세 (Request Schema)

### Headers
```http
POST /api/chat HTTP/1.1
Host: localhost:5000
Content-Type: application/json
Accept: text/event-stream, application/json
```

### Request Body
```json
{
  "block_key": "service_interpretation",
  "stock_code": "005930",
  "model_date": "2026-08-14",
  "session_id": "session-1234"
}
```

| 필드명 | 타입 | 필수 여부 | 유효성 검증 규칙 | 설명 |
| :--- | :--- | :---: | :--- | :--- |
| `block_key` | `string` | **Y** | `CHAT_BLOCK_DEFINITIONS`에 등록된 유효 키 | 선택된 질문 블록 식별자 |
| `stock_code` | `string` | N (종목 질문 시 Y) | 6자리 숫자 문자열 | 분석 대상 종목 코드 |
| `model_date` | `string` | N (종목 질문 시 Y) | `YYYY-MM-DD` ISO 포맷 | 분석 대상 기준일자 |
| `session_id` | `string` | N | 임의의 세션 문자열 | 사용자 대화 세션 식별자 |

---

## 3. 응답 명세 (Response Schema)

### 3.1 스트리밍 응답 헤더 (SSE Response Headers)
```http
HTTP/1.1 200 OK
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-cache, no-transform
Connection: keep-alive
X-Accel-Buffering: no
```

### 3.2 SSE 이벤트 스트림 시퀀스

#### Case 1: 정본 지식 캐시 히트 (즉각 반환, < 50ms)
캐시된 정본 질문의 경우 지연 없이 단일 완료 패킷을 전송하고 스트림을 종료합니다.
```text
data: {"type": "done", "status": "ready", "answer": "PILOS 서비스는 댓글 표현과 실제 개인투자자 수급의 연관성을 분석하는 연구 플랫폼입니다...", "route": "service_knowledge", "sources": [{"type": "service_document", "label": "PILOS 서비스 문서", "version": "1.0"}], "warnings": []}

data: [DONE]

```

#### Case 2: 동적 LLM 생성 (점진 스트리밍)
로컬 GPU가 토큰을 생성할 때마다 실시간으로 델타를 방출하고, 완결 시 `done` 메타데이터를 전송합니다.
```text
data: {"type": "token", "delta": "선택하신 "}

data: {"type": "token", "delta": "날짜의 "}

data: {"type": "token", "delta": "수급 분석 "}

data: {"type": "token", "delta": "결과입니다."}

data: {"type": "done", "status": "ready", "answer": "선택하신 날짜의 수급 분석 결과입니다.", "route": "stock_analysis", "stock_code": "005930", "as_of": "2026-08-14", "sources": [{"type": "llm_report", "label": "005930 2026-08-14 분석 보고서"}], "warnings": []}

data: [DONE]

```

#### Case 3: 에러 및 타임아웃 발생 (안전 폴백)
```text
data: {"type": "error", "status": "unavailable", "message": "현재 로컬 모델 응답이 지연되고 있습니다. 정본 문서의 요약을 안내해 드립니다.", "fallback_answer": "PILOS 분석 결과는 투자 권유가 아니며 ..."}

data: [DONE]

```

---

## 4. HTTP 상태 코드

| 상태 코드 | 의미 | 설명 |
| :--- | :--- | :--- |
| `200 OK` | 성공 (Stream Open) | SSE 연결이 수립되어 스트림 패킷 전송 시작 |
| `400 Bad Request` | 요청 검증 실패 | 필수 파라미터 누락, 유효하지 않은 `block_key` 또는 날짜 포맷 오류 |
| `404 Not Found` | 리소스 없음 | 유효하지 않은 종목 코드이거나 해당 데이터 부재 |
| `503 Service Unavailable` | 서비스 장애 | AI 모델 게이트웨이 완전 오프라인 및 폴백 불가 시 반환 |
