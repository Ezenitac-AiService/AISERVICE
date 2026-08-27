from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .guardrails.pii_filter import mask_pii


@dataclass(frozen=True)
class RetrievalDocument:
    source_review_id: int
    product_id: int
    text: str
    metadata: Mapping[str, object] = field(default_factory=dict)


def grounded_response(
    query: str,
    documents: list[RetrievalDocument],
    *,
    product_id: int | None = None,
    abstention_reason: str = "NO_CITABLE_SOURCE",
) -> dict[str, Any]:
    candidates = [
        document
        for document in documents
        if product_id is None or document.product_id == product_id
    ]
    if not candidates:
        return {
            "status": "abstained",
            "abstention_reason": abstention_reason,
            "answer": "검증 가능한 후기 근거가 없어 답변을 생성하지 않습니다.",
            "citations": [],
        }
    safe_query = mask_pii(query)
    citations = [
        {
            "source_review_id": document.source_review_id,
            "quote": mask_pii(document.text),
        }
        for document in candidates
    ]
    return {
        "status": "grounded",
        "answer": f"{safe_query}에 대한 검증된 후기 {len(candidates)}건을 확인했습니다.",
        "citations": citations,
    }
