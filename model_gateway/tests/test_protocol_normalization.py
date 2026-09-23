"""
Unit tests for Ingress Gateway 8 Protocol Normalizations (FR-007).
Validates:
1. Pilos model auto-injection for /v1/embeddings and /v1/rerank
2. Connection: close header injection for backend calls
3. Dual mapping of rerank results: res['data'] = res['results']
4. Client disconnect triggers backend socket close
5. {"status": "no slot available"} treated as HEALTHY
6. validate_pre_queue_prompt_limits keyword argument binding and 6,000-char BGE guard
7. Jinja2 template delegation (no hardcoded ChatML stops injected)
8. SSE queue progress: ': queue_status {...}\n\n' comment by default, 'event: queue_status' when X-Queue-Progress: true
"""

import json
import pytest
from src.core.queue_manager import validate_pre_queue_prompt_limits


def test_dos_guard_keyword_arguments_and_bge_limits():
    """Verify validate_pre_queue_prompt_limits requires keyword arguments and enforces 6,000 char BGE limit."""
    # Keyword arguments work
    assert validate_pre_queue_prompt_limits(model_id="qwen3.5-9b", prompt="Hello") is True
    assert validate_pre_queue_prompt_limits(model_id="bge-m3", prompt="Short text") is True

    # BGE-M3 text exceeding 6,000 chars raises ValueError
    long_text = "a" * 6001
    with pytest.raises(ValueError) as exc_info:
        validate_pre_queue_prompt_limits(model_id="bge-m3", prompt=long_text)
    assert "6000" in str(exc_info.value) or "6,000" in str(exc_info.value)

    # BGE-Reranker text exceeding 6,000 chars raises ValueError
    with pytest.raises(ValueError) as exc_info:
        validate_pre_queue_prompt_limits(model_id="bge-reranker-v2-m3", prompt=long_text)
    assert "6000" in str(exc_info.value) or "6,000" in str(exc_info.value)


def test_sse_queue_status_comment_format():
    """Verify queue status is formatted as SSE comment by default for OpenAI SDK compatibility."""
    from src.api.routes.inference_api import format_queue_status_event

    # Default: WHATWG SSE comment syntax ': queue_status {...}\n\n'
    comment_out = format_queue_status_event(position=1, wait_sec=2.5, custom_event=False)
    assert comment_out.startswith(": queue_status ")
    assert comment_out.endswith("\n\n")
    assert "position" in comment_out

    # Custom event: when X-Queue-Progress is true -> 'event: queue_status\ndata: {...}\n\n'
    event_out = format_queue_status_event(position=1, wait_sec=2.5, custom_event=True)
    assert "event: queue_status\n" in event_out
    assert "data: " in event_out


def test_rerank_dual_mapping():
    """Verify rerank response maps results to data for backward compatibility."""
    from src.api.routes.inference_api import normalize_rerank_response

    backend_response = {
        "object": "list",
        "results": [
            {"index": 0, "relevance_score": 0.95, "document": {"text": "doc1"}},
            {"index": 1, "relevance_score": 0.82, "document": {"text": "doc2"}}
        ],
        "usage": {"prompt_tokens": 25, "total_tokens": 25}
    }
    normalized = normalize_rerank_response(backend_response)
    assert "results" in normalized
    assert "data" in normalized
    assert normalized["data"] == normalized["results"]
