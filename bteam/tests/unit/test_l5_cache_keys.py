"""
Unit test for L5 cache key generation with qwen3.5-9b and cache flush on model upgrade (T031 / US3).
Validates:
- Default model_id in build_l5_key is 'qwen3.5-9b'
- Cache key format matches 'olliview:l5:{tenant}:{hash_32}'
- Cache keys for qwen3.5-9b are strictly distinct from legacy qwen3.5-2b keys
- Flush script logic targets 'olliview:l5:*' pattern
"""

import pytest
import inspect
from unittest.mock import MagicMock
from oliview_core.redis_pool import build_l5_key


def test_build_l5_key_default_model_is_9b():
    """US3: Default model_id for build_l5_key must be 'qwen3.5-9b'."""
    sig = inspect.signature(build_l5_key)
    model_param = sig.parameters.get("model_id")
    assert model_param is not None, "build_l5_key must have 'model_id' parameter"
    assert model_param.default == "qwen3.5-9b", f"Expected default 'qwen3.5-9b', got {model_param.default}"


def test_build_l5_key_hash_isolation_between_models():
    """US3: Cache keys generated for 9b must differ from 2b to prevent poisoned cross-model cache hits."""
    key_9b = build_l5_key(
        tenant_id="chata",
        rewritten_query="수분크림 추천해줘",
        doc_ids=["doc1", "doc2"],
        model_id="qwen3.5-9b"
    )
    key_2b = build_l5_key(
        tenant_id="chata",
        rewritten_query="수분크림 추천해줘",
        doc_ids=["doc1", "doc2"],
        model_id="qwen3.5-2b"
    )

    assert key_9b.startswith("olliview:l5:chata:")
    assert key_2b.startswith("olliview:l5:chata:")
    assert key_9b != key_2b, "9B and 2B cache keys must be strictly isolated by hash"


def test_flush_l5_cache_script_logic():
    """US3: Flush script must target 'olliview:l5:*' using SCAN and delete matching keys."""
    from scripts.flush_l5_cache import flush_l5_cache_keys

    mock_redis = MagicMock()
    # Mock SCAN returning batch of keys then 0 cursor
    mock_redis.scan.side_effect = [
        (10, [b"olliview:l5:chata:abc1", b"olliview:l5:chatb:abc2"]),
        (0, [b"olliview:l5:chata:abc3"]),
    ]
    mock_redis.delete.return_value = 2

    count = flush_l5_cache_keys(redis_client=mock_redis)
    assert count == 3
    assert mock_redis.scan.call_count == 2
    mock_redis.delete.assert_any_call(b"olliview:l5:chata:abc1", b"olliview:l5:chatb:abc2")
    mock_redis.delete.assert_any_call(b"olliview:l5:chata:abc3")
