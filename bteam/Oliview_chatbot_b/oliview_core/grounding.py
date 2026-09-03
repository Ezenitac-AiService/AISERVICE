"""Privacy-preserving RAG claim/citation validation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def assess_grounding(claims: Iterable[Mapping[str, Any]], citations: Iterable[Mapping[str, Any]], references: Iterable[Any]) -> dict[str, Any]:
    reference_list = list(references)
    claim_ids = [str(claim.get("claim_id", "")) for claim in claims if claim.get("claim_id")]
    claim_set = set(claim_ids)
    valid_claims: set[str] = set()
    accepted: list[dict[str, Any]] = []
    for citation in citations:
        claim_id = str(citation.get("claim_id", ""))
        document_id = str(citation.get("document_id", ""))
        try:
            result_index = int(citation.get("result_index", -1))
        except (TypeError, ValueError):
            continue
        if claim_id not in claim_set or not 0 <= result_index < len(reference_list):
            continue
        reference = reference_list[result_index]
        if document_id != str(getattr(reference, "review_id", "")):
            continue
        quote = citation.get("quote")
        if quote and str(quote) not in str(getattr(reference, "clean_text", "")):
            continue
        valid_claims.add(claim_id)
        accepted.append({"claim_id": claim_id, "document_id": document_id, "result_index": result_index})
    factual_count = len(claim_ids)
    cited_count = len(valid_claims)
    return {
        "factual_claim_count": factual_count,
        "cited_claim_count": cited_count,
        "unsupported_claim_count": factual_count - cited_count,
        "citation_coverage_percent": round(cited_count / factual_count * 100, 2) if factual_count else None,
        "claim_ids": claim_ids,
        "citations": accepted,
        "raw_content_logged": False,
    }


def abstention_evidence(*, response_status: str = "abstained") -> dict[str, Any]:
    return {
        "response_status": response_status,
        "model_invoked": False,
        "factual_claim_count": 0,
        "cited_claim_count": 0,
        "unsupported_claim_count": 0,
        "citation_coverage_percent": None,
        "claim_ids": [],
        "citations": [],
        "raw_content_logged": False,
    }

