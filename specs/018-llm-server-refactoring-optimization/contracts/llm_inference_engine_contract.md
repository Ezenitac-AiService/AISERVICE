# Contract: BaseInferenceEngine & OpenAI-Compatible Proxy Contract

## 1. `BaseInferenceEngine` Python Abstract Interface

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, AsyncGenerator

class BaseInferenceEngine(ABC):
    """Abstract Base Class for LLM/Auxiliary Inference Backends."""

    @abstractmethod
    async def load_model(self, model_id: str, n_ctx: int, **kwargs) -> Dict[str, Any]:
        """Loads model into GPU memory with target context window."""
        pass

    @abstractmethod
    async def unload_model(self) -> None:
        """Unloads current model and releases GPU VRAM."""
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        """Returns True if the backend is ready to accept requests."""
        pass

    @abstractmethod
    async def generate_stream(self, payload: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """Streams completion tokens or JSON events."""
        pass
```

## 2. API Endpoints & Request/Response Contract

### `POST /v1/chat/completions`
```json
{
  "model": "qwen3.5-4b",
  "messages": [
    {"role": "system", "content": "You are a helpful beauty advisor."},
    {"role": "user", "content": "식물나라 토너 분석해줘"}
  ],
  "max_tokens": 4096,
  "temperature": 0.3,
  "stream": true,
  "skip_thinking": false,
  "response_format": {"type": "text"}
}
```

### Response (Streaming SSE chunks):
```text
data: {"choices": [{"delta": {"content": "<think>\n식물나라 토너 리뷰 데이터 분석...\n"}}]}
data: {"choices": [{"delta": {"content": "</think>\n### 🌿 식물나라 토너 분석\n"}}]}
data: [DONE]
```
