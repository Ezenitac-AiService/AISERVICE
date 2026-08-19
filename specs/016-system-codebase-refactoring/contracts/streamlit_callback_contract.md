# Interface Contract: Streamlit Step Callback (`oliview_core.callback`)

**Feature**: [spec.md](../spec.md) | **Date**: 2026-08-19 | **Status**: Complete

---

## 1. Callback Contract

```python
from oliview_core.types import StepEvent

class StreamlitStepCallback:
    def __init__(self, status_box):
        self.status = status_box

    def on_step(self, event: StepEvent) -> None:
        """Writes live bullet points directly inside the st.status container."""
        self.status.write(f"- {event.label}")
```

---

## 2. Event Dispatching Order

1. `INTENT_ANALYSIS` → `- 🔍 질문 의도 및 화장품 속성 분석 중...`
2. `HYBRID_SEARCH` → `- 📚 관련 화장품 리뷰 및 성분 하이브리드 검색 중...`
3. `RERANKING` → `- 🧠 AI 심층 분석 및 BGE Cross-Encoder 리랭킹 중...`
4. `LLM_SYNTHESIS` → Status container updates to `✅ 리뷰 분석 및 검색 완료 (X.X초, 5건 선별)` and collapses `expanded=False`.
