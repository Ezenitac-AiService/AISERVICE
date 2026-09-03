"""Contract tests for anonymous rate limiting and fail-closed state store policy.

Enforces:
- FR-008a: IP rate limit (10/min), concurrent requests (2), body size (64KB), max tokens (16384).
- State store failure behavior: AI requests return 503, non-AI paths unaffected.
"""

from pathlib import Path
import pytest

def test_rate_limiter_defaults():
    """Verify rate limiter parameters match specification."""
    from AISERVICE.model_gateway.src.api.middleware import RateLimitConfig

    cfg = RateLimitConfig()
    assert cfg.ip_per_minute == 10
    assert cfg.concurrent_per_ip == 2
    assert cfg.max_body_bytes == 65536
    assert cfg.max_response_tokens == 16384
    assert cfg.timeout_seconds == 180

def test_body_size_rejection():
    """Requests exceeding 64KB body size must be rejected."""
    from AISERVICE.model_gateway.src.api.middleware import check_body_size

    small_body = b"x" * 1024
    large_body = b"x" * 70000

    assert check_body_size(len(small_body)) is True
    assert check_body_size(len(large_body)) is False

def test_redis_failure_fail_closed():
    """When Redis is unreachable, AI rate limiter must fail closed for AI routes."""
    from AISERVICE.model_gateway.src.api.middleware import evaluate_rate_limit_with_redis_error

    # AI route fail-closed: returns 503
    ai_status = evaluate_rate_limit_with_redis_error(is_ai_endpoint=True)
    assert ai_status == 503

    # Non-AI route: returns 200 (continues serving)
    web_status = evaluate_rate_limit_with_redis_error(is_ai_endpoint=False)
    assert web_status == 200
