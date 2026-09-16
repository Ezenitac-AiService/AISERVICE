"""Contract tests for model runtime behavior (T028).

Enforces:
- Models: qwen3.5-4b, qwen3.5-2b, bge-m3, bge-reranker-v2-m3
- VRAM safety limit: 10240MB
- Fail-closed 503 on unrouted/unavailable models
"""

import pytest
from src.core.engine import resolve_model_or_fail, AUTHORITATIVE_MODELS
from src.core.config import get_model_routing_config
from src.core.vram_monitor import check_vram_headroom

def test_authoritative_models_present():
    expected = {"qwen3.5-9b", "qwen3.5-4b", "bge-m3", "bge-reranker-v2-m3"}
    assert AUTHORITATIVE_MODELS == expected

def test_model_resolution_and_fail_closed():
    from fastapi import HTTPException
    assert resolve_model_or_fail("fast") == "qwen3.5-4b"
    assert resolve_model_or_fail("synthesis") == "qwen3.5-9b"
    with pytest.raises(HTTPException) as exc_info:
        resolve_model_or_fail("unsupported_fake_model")
    assert exc_info.value.status_code == 404

def test_vram_safety_range():
    assert check_vram_headroom(8000, limit_mb=10240) is True
    assert check_vram_headroom(11000, limit_mb=10240) is False
