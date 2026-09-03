"""Contract tests for model routing, aliases, and fail-closed policies.

Enforces:
- FR-001: Model routing keys and authoritative model identities.
- FR-003: Shared context pool and fail-closed 503 on unrouted/unavailable models.
- Single-model mode vs multi-model mode topology.
"""

from pathlib import Path
import pytest

ROUTING_KEYS = {
    "DEFAULT_MODEL": "qwen3.5-4b",
    "FAST_LLM_MODEL": "qwen3.5-2b",
    "SYNTHESIS_LLM_MODEL": "qwen3.5-4b",
    "EMBEDDING_MODEL": "bge-m3",
    "RERANK_MODEL": "bge-reranker-v2-m3",
}

def test_model_routing_keys_match_specification():
    """Verify standard SSOT routing keys and default model values."""
    from AISERVICE.model_gateway.src.core.config import get_model_routing_config

    cfg = get_model_routing_config()
    for key, expected_model in ROUTING_KEYS.items():
        assert cfg.get(key) == expected_model, f"Mismatch for {key}: expected {expected_model}, got {cfg.get(key)}"

def test_unregistered_model_fails_closed_with_503():
    """Requesting an unregistered or unavailable model must return 503 fail-closed (no silent fallback)."""
    from AISERVICE.model_gateway.src.core.engine import resolve_model_or_fail

    with pytest.raises(Exception) as exc_info:
        resolve_model_or_fail("non_existent_unregistered_model_xyz")
    assert "503" in str(exc_info.value) or "Unavailable" in str(exc_info.value)

def test_single_model_mode_routing():
    """In single model mode, fast and synthesis route to fast model or designated single model."""
    from AISERVICE.model_gateway.src.core.config import get_effective_model

    # When single_model_mode is True
    effective = get_effective_model("synthesis", single_model_mode=True)
    assert effective in {"qwen3.5-2b", "qwen3.5-4b"}
