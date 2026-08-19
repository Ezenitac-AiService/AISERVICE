# Interface Contracts: 챗봇 안정성 및 게이트웨이 복원 계약

**Feature**: `024-chatbot-gateway-stability-fix`
**Date**: 2026-08-20

---

## 1. Context Trimming Contract (`budget_context_documents`)

```python
def budget_context_documents(
    products: list, 
    model_name: str = "qwen3.5-4b", 
    max_budget_chars: int = 1500, 
    max_sentence_len: int = 150,
    max_total_chars: Optional[int] = None
) -> list:
    """
    Guarantees:
    1. 'is_9b' is strictly evaluated as ('9b' in str(model_name).lower()).
    2. Never raises NameError or AttributeError regardless of input structure.
    3. Trims total characters to budget without throwing exceptions.
    """
```

---

## 2. Gateway Self-Healing Contract (`ProcessManager.ensure_server_running`)

```python
def ensure_server_running(port: int = 8089) -> bool:
    """
    Guarantees:
    1. Checks if subprocess is alive.
    2. If dead (e.g. killed by OOM), cleans up and relaunches subprocess immediately.
    3. Waits up to 5 seconds for healthcheck ping before returning status.
    """
```
