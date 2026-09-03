"""Anonymous AI gateway limits are enforced before proxying."""

from gateway.proxy_policy import AnonymousAIRateLimiter


def test_rate_limit_contract_matches_demo_defaults() -> None:
    limiter = AnonymousAIRateLimiter()
    first = limiter.admit("203.0.113.10", body_bytes=64 * 1024, output_tokens=16_384, now=0)
    second = limiter.admit("203.0.113.10", body_bytes=1, output_tokens=1, now=1)
    third = limiter.admit("203.0.113.10", body_bytes=1, output_tokens=1, now=2)
    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.reason == "concurrency"
    limiter.complete("203.0.113.10")
    limiter.complete("203.0.113.10")


def test_body_and_output_limits_return_429() -> None:
    limiter = AnonymousAIRateLimiter()
    assert limiter.admit("203.0.113.11", body_bytes=64 * 1024 + 1, output_tokens=1).status_code == 429
    assert limiter.admit("203.0.113.11", body_bytes=1, output_tokens=16_385).status_code == 429


def test_per_ip_minute_limit_is_independent() -> None:
    limiter = AnonymousAIRateLimiter(requests_per_minute=2)
    for second in (0, 1):
        decision = limiter.admit("203.0.113.12", body_bytes=1, output_tokens=1, now=second)
        assert decision.allowed
    assert limiter.admit("203.0.113.12", body_bytes=1, output_tokens=1, now=2).reason == "requests_per_minute"
    assert limiter.admit("203.0.113.13", body_bytes=1, output_tokens=1, now=2).allowed

