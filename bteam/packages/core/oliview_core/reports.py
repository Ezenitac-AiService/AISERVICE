from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, cast

from .guardrails.pii_filter import mask_pii


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _validate_citation(
    citation: Mapping[str, Any],
    *,
    product_id: int | str,
    reviews: Mapping[int | str, Mapping[str, Any]],
) -> None:
    source_id = cast(int | str | None, citation.get("source_review_id"))
    if source_id is None:
        raise ValueError("citation source review does not exist")
    review = reviews.get(source_id)
    if review is None:
        review = reviews.get(int(source_id)) if str(source_id).isdigit() else None
    if review is None:
        raise ValueError("citation source review does not exist")
    if str(review.get("product_id")) != str(product_id):
        raise ValueError("citation source review belongs to another product")
    quote = str(citation.get("quote", ""))
    if quote and mask_pii(quote) != quote:
        raise ValueError("citation quote contains unmasked PII")
    if quote and _normalized(quote) not in _normalized(
        str(review.get("review_content", ""))
    ):
        raise ValueError(
            "citation quote is not a normalized substring of the source review"
        )


def validate_report(
    report: Mapping[str, Any], *, reviews: Mapping[int | str, Mapping[str, Any]]
) -> dict[str, Any]:
    product_id = cast(int | str | None, report.get("product_id"))
    if product_id is None:
        raise ValueError("report product_id is required")
    claims = report.get("claims") or []
    claim_ids = {str(claim.get("claim_id")) for claim in claims}
    status = str(report.get("report_status", report.get("status", ""))).lower()
    for claim in claims:
        citations = claim.get("citations") or []
        if not citations:
            raise ValueError("grounded claims require at least one citation")
        for citation in citations:
            _validate_citation(citation, product_id=product_id, reviews=reviews)
        claim_type = str(claim.get("claim_type", ""))
        if claim_type in {"complaint", "praise"} and not claim.get("claim_id"):
            raise ValueError("complaint/praise claim requires claim_id")
    for suggestion in report.get("improvement_suggestions") or []:
        for basis in suggestion.get("basis_claim_ids") or []:
            if str(basis) not in claim_ids:
                raise ValueError("suggestion basis claim does not exist")
    for field in ("key_complaints", "key_praises"):
        if any(str(claim_id) not in claim_ids for claim_id in report.get(field) or []):
            raise ValueError(f"{field} contains a dangling claim reference")
    if status == "abstained" and claims:
        raise ValueError("abstained report cannot include grounded claims")
    if not claims and status != "abstained":
        raise ValueError("report without claims must be explicitly abstained")
    return dict(report)


def legacy_report_projection(report: Mapping[str, Any]) -> dict[str, Any]:
    projected = dict(report)
    projected.setdefault("schema_version", 2)
    projected.setdefault("abstention_reason", "LEGACY_UNVERIFIED")
    projected.setdefault("claims", [])
    return projected
