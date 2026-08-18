# Data Model: 올리챗·올원챗 임베딩 타임아웃 해소 및 순차 대기 큐 (009-fix-ollychat-embedding-timeout)

## 1. Concurrency & Queue State Data Model

### `LLMQueueStatus`
순차 대기 큐의 현재 상태를 표현하는 데이터 모델.

```python
class LLMQueueStatus(BaseModel):
    queue_length: int = Field(description="현재 큐에서 대기 중인 요청 수")
    is_busy: bool = Field(description="GPU가 현재 추론을 수행 중인지 여부")
    current_request_id: Optional[str] = Field(default=None, description="현재 추론 중인 요청 ID")
    estimated_wait_seconds: float = Field(description="예상 대기 시간(초)")
```

### `StreamingKeepAlivePacket`
큐 대기 중 클라이언트 소켓 타임아웃을 방지하기 위해 전송되는 킵얼라이브 패킷.

```python
class StreamingKeepAlivePacket(BaseModel):
    type: Literal["status", "token", "done", "error"] = Field(description="이벤트 타입")
    content: str = Field(description="상태 메시지 또는 생성 토큰")
    queue_position: Optional[int] = Field(default=None, description="대기 순번")
```

---

## 2. Process Manager I/O Redirection Configuration

### `ProcessIORedirection`
서브프로세스의 stdout/stderr를 OS 파일 디스크립터에 직접 연결하는 설정 구조체.

```python
class ProcessIORedirection(BaseModel):
    log_file_path: str = Field(description="로그 파일의 절대 경로")
    mode: str = Field(default="a", description="파일 열기 모드")
    use_direct_fd: bool = Field(default=True, description="파이프 대신 직접 파일 디스크립터 사용 여부")
```

---

## 3. Multi-Chatbot Regression Test Results Model

### `ChatbotHealthReport`
3대 챗봇의 통합 회귀 검증 결과를 담는 데이터 모델.

```python
class ChatbotHealthReport(BaseModel):
    service_name: str = Field(description="챗봇 명칭 (pilos, oliview_chata, oliview_chatb)")
    status_code: int = Field(description="HTTP 응답 코드 (200, 500 등)")
    latency_ms: float = Field(description="응답 지연 시간 (밀리초)")
    is_success: bool = Field(description="기능 검증 성공 여부")
    error_message: Optional[str] = Field(default=None, description="실패 시 에러 메시지")
```
