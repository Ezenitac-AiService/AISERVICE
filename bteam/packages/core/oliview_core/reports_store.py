from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from copy import deepcopy
from typing import Any

from .reports import legacy_report_projection, validate_report


class InMemoryReportStore:
    """Transactional adapter used by local rehearsal; production maps the same API to MySQL."""

    def __init__(self) -> None:
        self.reports: dict[int, dict[str, Any]] = {}

    @contextmanager
    def transaction(self) -> Iterator[dict[int, dict[str, Any]]]:
        working = deepcopy(self.reports)
        yield working
        self.reports = working

    def save(
        self,
        report: Mapping[str, Any],
        *,
        reviews: Mapping[int | str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        prepared = validate_report(report, reviews=reviews)
        report_id = int(prepared["report_id"])
        with self.transaction() as working:
            working[report_id] = deepcopy(dict(prepared))
        return deepcopy(prepared)

    def get(self, report_id: int) -> dict[str, Any] | None:
        report = self.reports.get(report_id)
        return legacy_report_projection(report) if report is not None else None
