"""Trusted-proxy client IP and anonymous AI admission policy."""

from __future__ import annotations

import ipaddress
import threading
import time
from dataclasses import dataclass
from collections import defaultdict, deque
from collections.abc import Mapping


def parse_trusted_proxy_cidrs(value: str | list[str] | tuple[str, ...]) -> tuple[ipaddress._BaseNetwork, ...]:
    """Parse configured proxy networks; invalid entries fail closed."""

    values = [part.strip() for part in value.split(",")] if isinstance(value, str) else list(value)
    networks: list[ipaddress._BaseNetwork] = []
    for entry in values:
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError as exc:
            raise ValueError("invalid trusted proxy CIDR") from exc
    return tuple(networks)


def _is_trusted(peer_ip: str, networks: tuple[ipaddress._BaseNetwork, ...]) -> bool:
    try:
        address = ipaddress.ip_address(peer_ip)
    except ValueError:
        return False
    return any(address in network for network in networks)


def resolve_client_ip(
    peer_ip: str,
    headers: Mapping[str, str],
    *,
    trusted_proxy_cidrs: str | list[str] | tuple[str, ...],
    client_ip_header: str = "X-Forwarded-For",
) -> str:
    """Use a forwarded address only when the socket peer is trusted.

    A malformed or multi-hop header is rejected and the socket peer is used.
    The function returns a normalized address, never an arbitrary header value.
    """

    try:
        peer = ipaddress.ip_address(peer_ip)
    except ValueError:
        return peer_ip
    networks = parse_trusted_proxy_cidrs(trusted_proxy_cidrs)
    if not _is_trusted(str(peer), networks):
        return str(peer)
    raw = headers.get(client_ip_header, "").strip()
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if len(parts) != 1:
        return str(peer)
    try:
        return str(ipaddress.ip_address(parts[0]))
    except ValueError:
        return str(peer)


def resolve_client_ip_from_environment(peer_ip: str, headers: Mapping[str, str], environment: Mapping[str, str]) -> str:
    """Resolve using the same injected env consumed by the Nginx renderer."""

    return resolve_client_ip(
        peer_ip,
        headers,
        trusted_proxy_cidrs=environment.get("TRUSTED_PROXY_CIDRS", ""),
        client_ip_header=environment.get("TRUSTED_CLIENT_IP_HEADER", "X-Forwarded-For"),
    )


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    status_code: int
    reason: str


class AnonymousAIRateLimiter:
    """Small defense-in-depth limiter matching the gateway contract.

    Redis-backed deployments can wrap the same decision contract; this local
    implementation is intentionally fail-closed and is used for unit/contract
    validation without requiring a live Redis service.
    """

    def __init__(
        self,
        *,
        requests_per_minute: int = 10,
        max_concurrent: int = 2,
        body_limit_bytes: int = 64 * 1024,
        output_token_limit: int = 16_384,
    ) -> None:
        self.requests_per_minute = requests_per_minute
        self.max_concurrent = max_concurrent
        self.body_limit_bytes = body_limit_bytes
        self.output_token_limit = output_token_limit
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._active: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def admit(self, client_ip: str, *, body_bytes: int, output_tokens: int, now: float | None = None) -> RateDecision:
        if body_bytes > self.body_limit_bytes:
            return RateDecision(False, 429, "body_limit")
        if output_tokens > self.output_token_limit:
            return RateDecision(False, 429, "output_token_limit")
        current = time.monotonic() if now is None else now
        with self._lock:
            history = self._requests[client_ip]
            while history and history[0] <= current - 60:
                history.popleft()
            if len(history) >= self.requests_per_minute:
                return RateDecision(False, 429, "requests_per_minute")
            if self._active[client_ip] >= self.max_concurrent:
                return RateDecision(False, 429, "concurrency")
            history.append(current)
            self._active[client_ip] += 1
            return RateDecision(True, 200, "allowed")

    def complete(self, client_ip: str) -> None:
        with self._lock:
            self._active[client_ip] = max(0, self._active[client_ip] - 1)
