# Interface Contract: RAG 수명 주기 콜백 프로토콜 (Step Callback Protocol)

**Feature**: `014-ollychat-process-visualization`  
**Language**: Python 3.10+  
**Target Files**: `bteam/Oliview_chatbot_a/05.chatbot.py`, `06.app.py`, `project_ragapi.py`  

---

## 1. 개요

RAG 파이프라인 엔진(`05.chatbot.py`, `project_ragapi.py`)과 UI 레이어(Streamlit `st.status`, FastAPI SSE 스트리머) 간의 결합도를 낮추고 단계별 이벤트를 표준화하기 위한 Python Callback Protocol 규격입니다.

---

## 2. 프로토콜 정의 (Python Protocol)

```python
from __future__ import annotations
from typing import Any, Callable, Generator, List, Optional, Protocol, runtime_checkable
from dataclasses import dataclass
from enum import Enum


class PipelinePhase(str, Enum):
    INTENT_ANALYSIS = "INTENT_ANALYSIS"
    HYBRID_SEARCH = "HYBRID_SEARCH"
    RERANKING = "RERANKING"
    LLM_SYNTHESIS = "LLM_SYNTHESIS"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


@dataclass
class StepEvent:
    phase: PipelinePhase
    label: str
    status: str  # "running" | "complete" | "warning" | "error"
    elapsed_sec: float
    progress_percent: int
    message: Optional[str] = None
    extra_data: Optional[dict[str, Any]] = None


@runtime_checkable
class StepCallbackProtocol(Protocol):
    """RAG 파이프라인 단계별 이벤트 수신 프로토콜"""
    
    def on_step(self, event: StepEvent) -> None:
        """새로운 단계 진입 또는 상태 변경 시 호출"""
        ...
        
    def on_token(self, token: str) -> None:
        """4단계 LLM 답변 토큰 생성 시 실시간 호출"""
        ...
        
    def on_complete(self, metadata: dict[str, Any]) -> None:
        """전체 RAG 파이프라인 완료 시 메타데이터와 함께 호출"""
        ...
        
    def on_error(self, error_event: StepEvent) -> None:
        """예외 또는 검색 0건 발생 시 호출"""
        ...
```

---

## 3. 구현체 예시 (Implementations)

### 3.1 StreamlitStepCallback (올리챗 A용)
```python
class StreamlitStepCallback:
    def __init__(self, status_container):
        self.status = status_container
        self.start_time = time.time()
        
    def on_step(self, event: StepEvent):
        # st.status 라벨 및 내부 로그 업데이트
        self.status.write(f"{event.label}")
        
    def on_complete(self, metadata: dict[str, Any]):
        elapsed = metadata.get("total_latency_sec", 0.0)
        review_count = metadata.get("selected_review_count", 0)
        self.status.update(
            label=f"✅ 리뷰 종합 분석 완료 ({elapsed:.1f}초, {review_count}건 참조)",
            state="complete",
            expanded=False
        )
```

### 3.2 AsyncQueueCallback (올리챗 B FastAPI SSE용)
```python
class AsyncQueueCallback:
    def __init__(self, event_queue: asyncio.Queue):
        self.queue = event_queue
        
    async def on_step(self, event: StepEvent):
        await self.queue.put({"event": "step", "data": event.__dict__})
```

---

## 4. 함수 시그니처 확장 규칙

`05.chatbot.py`의 `generate_chatbot_answer` 및 `answer_question` 함수는 선택적 `callback: Optional[StepCallbackProtocol] = None` 파라미터를 추가하여, 기존 호출 코드와의 100% 하위 호환성을 보장합니다.
