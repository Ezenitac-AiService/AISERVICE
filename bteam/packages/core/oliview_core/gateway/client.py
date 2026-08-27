from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Semaphore
from typing import Any

from oliview_core.retry import RetryPolicy

from . import GatewayPool


@dataclass(frozen=True)
class GatewayResponse:
    endpoint: str
    attempts: int
    value: Any


class GatewayClient:
    def __init__(
        self,
        endpoints: list[Mapping[str, object]],
        *,
        retry: RetryPolicy | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.pool = GatewayPool(endpoints)
        self.retry = retry or RetryPolicy()
        self.sleeper = sleeper
        self._semaphores = {
            endpoint.url: Semaphore(endpoint.concurrency_limit)
            for endpoint in self.pool.endpoints
        }

    def call(self, operation: Callable[[str], Any]) -> GatewayResponse:
        last_error: Exception | None = None
        for attempt in range(1, self.retry.max_attempts + 1):
            endpoint = self.pool.next()
            try:
                semaphore = self._semaphores[endpoint.url]
                with semaphore, ThreadPoolExecutor(max_workers=1) as executor:
                    value = executor.submit(operation, endpoint.url).result(
                        timeout=endpoint.timeout_seconds
                    )
                return GatewayResponse(endpoint.url, attempt, value)
            except Exception as error:  # noqa: BLE001 - retry boundary
                last_error = error
                self.pool.mark_unhealthy(endpoint.url)
                if attempt < self.retry.max_attempts:
                    self.sleeper(self.retry.delay_for(attempt))
        raise RuntimeError("all model gateway attempts failed") from last_error
