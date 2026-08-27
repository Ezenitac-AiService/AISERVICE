import pytest
from oliview_core.gateway import GatewayPool, validate_production_topology


def test_production_requires_two_distinct_healthy_gpu_endpoints():
    endpoints = [
        {"url": "http://gpu-a", "gpu_instance": "a", "healthy": True},
        {"url": "http://gpu-b", "gpu_instance": "b", "healthy": True},
    ]
    validate_production_topology(endpoints, redis_ha_ready=True)
    pool = GatewayPool(endpoints)
    assert {pool.next().url, pool.next().url} == {"http://gpu-a", "http://gpu-b"}


def test_production_rejects_single_gpu_endpoint():
    with pytest.raises(ValueError):
        validate_production_topology(
            [{"url": "http://gpu-a", "gpu_instance": "a", "healthy": True}],
            redis_ha_ready=True,
        )
