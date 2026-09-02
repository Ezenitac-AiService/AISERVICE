import pytest


def test_auth_principal_and_redis_limiter_red_gate():
    """RED GATE: Asserts rate_limit.py provides atomic distributed rate limiter and concurrency lease."""
    try:
        from oliview_core.rate_limit import RedisRateLimiter  # type: ignore
        limiter = RedisRateLimiter(redis_url="redis://127.0.0.1:6379/0")
        assert hasattr(limiter, "check_rate_limit")
        assert hasattr(limiter, "acquire_concurrency_lease")
    except (ImportError, AttributeError) as exc:
        pytest.fail(f"RED GATE: RedisRateLimiter not implemented in oliview_core.rate_limit: {exc}")


def test_effective_caps_calculation_red_gate():
    """RED GATE: Asserts effective = min(client_request, server_cap) for timeout and tokens."""
    try:
        from oliview_core.security import compute_effective_limits  # type: ignore
        limits = compute_effective_limits(
            client_timeout_ms=30000,
            server_timeout_cap_ms=20000,
            client_output_tokens=4096,
            server_output_token_cap=2048,
        )
        assert limits["effective_timeout_ms"] == 20000
        assert limits["effective_max_output_tokens"] == 2048
    except (ImportError, AttributeError) as exc:
        pytest.fail(f"RED GATE: compute_effective_limits not implemented in oliview_core.security: {exc}")
