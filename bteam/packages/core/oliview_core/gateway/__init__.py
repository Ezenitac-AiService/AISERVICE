from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from threading import Lock
from typing import cast
from urllib.request import urlopen


@dataclass(frozen=True)
class GatewayEndpoint:
    url: str
    gpu_instance: str = "unknown"
    healthy: bool = True
    concurrency_limit: int = 1
    timeout_seconds: float = 30.0

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> GatewayEndpoint:
        return cls(
            url=str(value["url"]),
            gpu_instance=str(value.get("gpu_instance", "unknown")),
            healthy=bool(value.get("healthy", True)),
            concurrency_limit=int(cast(int | str, value.get("concurrency_limit", 1))),
            timeout_seconds=float(
                cast(float | str, value.get("timeout_seconds", 30.0))
            ),
        )


class GatewayPool:
    def __init__(self, endpoints: Iterable[Mapping[str, object] | GatewayEndpoint]):
        self.endpoints = tuple(
            item
            if isinstance(item, GatewayEndpoint)
            else GatewayEndpoint.from_mapping(item)
            for item in endpoints
        )
        self._index = 0
        self._lock = Lock()

    def healthy(self) -> tuple[GatewayEndpoint, ...]:
        return tuple(endpoint for endpoint in self.endpoints if endpoint.healthy)

    def mark_unhealthy(self, url: str) -> None:
        self.endpoints = tuple(
            GatewayEndpoint(
                endpoint.url,
                endpoint.gpu_instance,
                False if endpoint.url == url else endpoint.healthy,
                endpoint.concurrency_limit,
                endpoint.timeout_seconds,
            )
            for endpoint in self.endpoints
        )

    def probe(self, *, timeout: float = 2.0) -> tuple[GatewayEndpoint, ...]:
        probed: list[GatewayEndpoint] = []
        for endpoint in self.endpoints:
            try:
                with urlopen(f"{endpoint.url.rstrip('/')}/health", timeout=timeout):
                    healthy = True
            except OSError:
                healthy = False
            probed.append(
                GatewayEndpoint(
                    endpoint.url,
                    endpoint.gpu_instance,
                    healthy,
                    endpoint.concurrency_limit,
                    endpoint.timeout_seconds,
                )
            )
        self.endpoints = tuple(probed)
        return self.healthy()

    def next(self) -> GatewayEndpoint:
        healthy = self.healthy()
        if not healthy:
            raise RuntimeError("no healthy model gateway endpoint")
        with self._lock:
            endpoint = healthy[self._index % len(healthy)]
            self._index += 1
            return endpoint


def validate_production_topology(
    endpoints: Iterable[Mapping[str, object] | GatewayEndpoint], *, redis_ha_ready: bool
) -> None:
    normalized = tuple(
        item
        if isinstance(item, GatewayEndpoint)
        else GatewayEndpoint.from_mapping(item)
        for item in endpoints
    )
    distinct_gpu = {
        endpoint.gpu_instance for endpoint in normalized if endpoint.healthy
    }
    if len(distinct_gpu) < 2:
        raise ValueError(
            "PRODUCTION requires two healthy endpoints on distinct GPU instances"
        )
    if not redis_ha_ready:
        raise ValueError("PRODUCTION requires Redis HA quorum")
