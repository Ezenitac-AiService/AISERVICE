from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from oliview_core.reports import validate_report

from ..model_adapters import GatewayReportGenerator

__all__ = ["GatewayReportGenerator", "build_report", "validate_and_prepare"]


def build_report(
    *,
    product_id: int,
    claims: list[dict[str, Any]],
    improvement_suggestions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    report = {
        "schema_version": 2,
        "product_id": product_id,
        "status": "grounded" if claims else "abstained",
        "abstention_reason": None if claims else "NO_VERIFIED_EVIDENCE",
        "claims": claims,
        "improvement_suggestions": improvement_suggestions or [],
        "generated_at": datetime.now(UTC).isoformat(),
    }
    return report


def validate_and_prepare(
    report: Mapping[str, Any], reviews: Mapping[int | str, Mapping[str, Any]]
) -> dict[str, Any]:
    return validate_report(report, reviews=reviews)
