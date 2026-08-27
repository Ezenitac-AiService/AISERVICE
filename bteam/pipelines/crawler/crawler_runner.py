from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class CrawlCandidate:
    product_id: int
    source_key: str
    due: bool = True


class JsonReviewCrawler:
    """HTTP adapter for the existing review crawler service."""

    def __init__(self, endpoint: str):
        normalized = endpoint.strip().rstrip("/")
        if not normalized:
            raise ValueError("review crawler endpoint is required")
        self.endpoint = normalized

    def fetch(
        self, product_id: int, product_code: str, since: datetime
    ) -> dict[str, object]:
        query = urlencode(
            {
                "product_id": int(product_id),
                "product_code": product_code,
                "since": since.isoformat(),
            }
        )
        request = Request(f"{self.endpoint}?{query}", method="GET")
        with urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if isinstance(payload, list):
            return {"reviews": payload}
        if not isinstance(payload, dict):
            raise TypeError("review crawler response must be an object or list")
        return dict(payload)


def select_due_products(
    candidates: Iterable[CrawlCandidate],
) -> tuple[CrawlCandidate, ...]:
    return tuple(candidate for candidate in candidates if candidate.due)


def begin_cycle_watermark() -> datetime:
    return datetime.now(UTC)


def normalized_product_key(value: str) -> str:
    return " ".join(value.casefold().split())


def master_product_upsert(rows: Iterable[Mapping[str, object]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        key = normalized_product_key(str(row.get("source_key", row.get("name", ""))))
        if key:
            result[key] = int(cast(int | str, row.get("product_id", 0)))
    return result
