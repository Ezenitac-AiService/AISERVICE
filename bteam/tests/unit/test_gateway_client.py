from __future__ import annotations

from oliview_core.gateway.client import GatewayClient
from oliview_core.retry import RetryPolicy


def test_gateway_retry_moves_to_a_different_healthy_endpoint():
    calls: list[str] = []

    def operation(url: str) -> str:
        calls.append(url)
        if url.endswith("a"):
            raise OSError("endpoint down")
        return "ok"

    client = GatewayClient(
        [
            {
                "url": "http://gpu-a",
                "gpu_instance": "a",
                "healthy": True,
                "timeout_seconds": 1,
            },
            {
                "url": "http://gpu-b",
                "gpu_instance": "b",
                "healthy": True,
                "timeout_seconds": 1,
            },
        ],
        retry=RetryPolicy(max_attempts=2, base_seconds=0, cap_seconds=0),
        sleeper=lambda _seconds: None,
    )
    response = client.call(operation)
    assert response.value == "ok"
    assert calls == ["http://gpu-a", "http://gpu-b"]
