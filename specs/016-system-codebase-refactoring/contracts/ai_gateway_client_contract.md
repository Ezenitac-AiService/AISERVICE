# Interface Contract: AI Gateway Client (`oliview_core.client`)

**Feature**: [spec.md](../spec.md) | **Date**: 2026-08-19 | **Status**: Complete

---

## 1. Client Protocol Definition

```python
from typing import List, Iterator, AsyncIterator

class AiGatewayClient:
    """Unified HTTP Client for vLLM Inference, BGE-M3 Embeddings, and BGE-Reranker."""

    # Synchronous API (for Streamlit & Worker)
    def embed(self, texts: List[str]) -> List[List[float]]: ...
    def rerank(self, query: str, documents: List[str]) -> List[float]: ...
    def generate_stream(self, prompt: str, system_prompt: str = "", max_tokens: int = 2048) -> Iterator[str]: ...
    
    # Asynchronous API (for FastAPI & SSE)
    async def aembed(self, texts: List[str]) -> List[List[float]]: ...
    async def arerank(self, query: str, documents: List[str]) -> List[float]: ...
    async def agenerate_stream(self, prompt: str, system_prompt: str = "", max_tokens: int = 2048) -> AsyncIterator[str]: ...
```

---

## 2. Remote Reranker Endpoint Contract (`port 8091`)

- **Method**: `POST /v1/embeddings`
- **Request**:
  ```json
  {
    "model": "bge-reranker-v2-m3",
    "input": ["query text", "document 1", "document 2"]
  }
  ```
- **Response**:
  ```json
  {
    "data": [
      {"embedding": [0.012, -0.045, ...]},
      {"embedding": [0.034, -0.012, ...]}
    ]
  }
  ```
- **Score Computation**:
  ```python
  sim = np.dot(q_vec, d_vec) / (norm_q * norm_d)
  ```
