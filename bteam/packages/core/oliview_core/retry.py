from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_seconds: float = 0.5
    cap_seconds: float = 8.0
    heartbeat_seconds: int = 15
    ttl_seconds: int = 60

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if self.base_seconds < 0 or self.cap_seconds < 0:
            raise ValueError("backoff values must be non-negative")
        if self.cap_seconds < self.base_seconds:
            raise ValueError("cap_seconds must be >= base_seconds")
        if self.heartbeat_seconds <= 0:
            raise ValueError("heartbeat_seconds must be positive")
        if self.ttl_seconds < 3 * self.heartbeat_seconds:
            raise ValueError("ttl_seconds must be at least three heartbeats")

    def delay_for(self, attempt: int) -> float:
        if attempt < 1:
            raise ValueError("attempt is one-based")
        if attempt > self.max_attempts:
            return self.cap_seconds
        return min(self.cap_seconds, self.base_seconds * (2 ** (attempt - 1)))
