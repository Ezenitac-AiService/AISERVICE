import pytest
from oliview_core.retry import RetryPolicy


def test_retry_policy_requires_ttl_at_least_three_heartbeats():
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=3, heartbeat_seconds=15, ttl_seconds=44)


def test_retry_policy_caps_attempts_and_backoff():
    policy = RetryPolicy(
        max_attempts=3,
        base_seconds=0.2,
        cap_seconds=2.0,
        heartbeat_seconds=15,
        ttl_seconds=60,
    )
    assert policy.max_attempts == 3
    assert policy.delay_for(1) == pytest.approx(0.2)
    assert policy.delay_for(4) == pytest.approx(2.0)
