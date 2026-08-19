# Interface Contract: Core Pipeline (`oliview_core.pipeline`)

**Feature**: [spec.md](../spec.md) | **Date**: 2026-08-19 | **Status**: Complete

---

## 1. Pipeline Function Signatures

```python
from typing import Iterator, Tuple, Optional
from oliview_core.types import RagExecutionMetadata, StepEvent

class StepCallbackProtocol:
    def on_step(self, event: StepEvent) -> None:
        """Callback invoked whenever a search/reranking step progress occurs."""
        ...

def prepare_pipeline_stream(
    question: str,
    callback: Optional[StepCallbackProtocol] = None,
    product_hint: Optional[str] = None,
) -> Tuple[Iterator[str], RagExecutionMetadata]:
    """
    Executes synchronous RAG retrieval stages 1~3:
      1. Intent & attribute parsing
      2. Hybrid search (Faiss dense + BM25 + category filters)
      3. BGE Reranking (GPU remote 8091 with CPU fallback)
    
    Notifies callback at each step.
    
    Returns:
      - token_stream_generator: Iterator[str] to be passed to st.write_stream or SSE loop
      - metadata: RagExecutionMetadata containing reference reviews and latencies
    """
    ...
```

---

## 2. Invocation Contract

```python
# In Streamlit (ChatA):
with st.status("🔍 질문 의도 및 화장품 속성 분석 중...", expanded=True) as status_box:
    callback = StreamlitStepCallback(status_box)
    token_gen, meta = prepare_pipeline_stream(question=cleaned_question, callback=callback)
    status_box.update(
        label=f"✅ 리뷰 분석 및 검색 완료 ({meta.total_latency_sec:.1f}초, {meta.selected_review_count}건 선별)",
        state="complete",
        expanded=False,
    )

answer = st.write_stream(token_gen)
```
