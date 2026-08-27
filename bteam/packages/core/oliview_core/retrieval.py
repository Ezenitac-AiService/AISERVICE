"""Dependency-light hybrid retrieval and deterministic reranking."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any

from .guardrails.pii_filter import mask_pii
from .rag import RetrievalDocument


def _tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    tokens = set(re.findall(r"[^\W_]+", normalized, flags=re.UNICODE))
    for token in tuple(tokens):
        if len(token) > 2:
            tokens.update(token[index : index + 2] for index in range(len(token) - 1))
    return tokens


def lexical_score(query: str, text: str) -> float:
    query_tokens = _tokens(query)
    text_tokens = _tokens(text)
    if not query_tokens or not text_tokens:
        return 0.0
    overlap = len(query_tokens & text_tokens) / len(query_tokens)
    exact_bonus = (
        0.2
        if unicodedata.normalize("NFKC", query).casefold().strip()
        in unicodedata.normalize("NFKC", text).casefold()
        else 0.0
    )
    return min(1.0, overlap + exact_bonus)


def _as_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _metadata_dict(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def hybrid_retrieve(
    query: str,
    documents: Iterable[RetrievalDocument],
    vector_rows: Iterable[Mapping[str, object]] = (),
    *,
    product_id: int | None = None,
    limit: int = 6,
) -> list[dict[str, object]]:
    merged: dict[tuple[int, int], dict[str, Any]] = {}

    for document in documents:
        if product_id is not None and document.product_id != product_id:
            continue
        key = (document.source_review_id, document.product_id)
        merged[key] = {
            "source_review_id": document.source_review_id,
            "product_id": document.product_id,
            "text": document.text,
            "metadata": dict(document.metadata),
            "vector_rank": None,
        }

    for vector_rank, row in enumerate(vector_rows, start=1):
        source_id = _as_int(row.get("source_review_id", row.get("review_id")))
        row_product_id = _as_int(row.get("product_id"))
        if source_id is None or row_product_id is None:
            continue
        if product_id is not None and row_product_id != product_id:
            continue
        key = (source_id, row_product_id)
        existing = merged.setdefault(
            key,
            {
                "source_review_id": source_id,
                "product_id": row_product_id,
                "text": str(row.get("text", "")),
                "metadata": {},
                "vector_rank": None,
            },
        )
        if not existing.get("text") and row.get("text"):
            existing["text"] = str(row["text"])
        existing["metadata"] = _metadata_dict(row.get("metadata", {}))
        existing["vector_rank"] = vector_rank

    if not merged:
        return []

    max_vector_rank = max(
        (
            int(str(row["vector_rank"]))
            for row in merged.values()
            if row["vector_rank"] is not None
        ),
        default=0,
    )
    ranked: list[dict[str, Any]] = []
    for row in merged.values():
        text = str(row.get("text", ""))
        lexical = lexical_score(query, text)
        rank_value = row.get("vector_rank")
        vector = (
            (1.0 - (int(str(rank_value)) - 1) / max_vector_rank)
            if rank_value and max_vector_rank
            else 0.0
        )
        combined = 0.65 * lexical + 0.35 * vector
        if lexical == 0.0 and vector == 0.0:
            continue
        ranked.append(
            {
                "source_review_id": int(row["source_review_id"]),
                "product_id": int(row["product_id"]),
                "text": mask_pii(text),
                "metadata": _metadata_dict(row.get("metadata", {})),
                "lexical_score": round(lexical, 6),
                "vector_score": round(vector, 6),
                "retrieval_score": round(combined, 6),
            }
        )

    ranked.sort(
        key=lambda row: (
            -float(row["retrieval_score"]),
            -float(row["lexical_score"]),
            int(row["source_review_id"]),
        )
    )
    results = ranked[: max(0, int(limit))]
    for index, row in enumerate(results, start=1):
        row["rank"] = index
        row["rerank_score"] = round(
            0.75 * float(row["lexical_score"]) + 0.25 * float(row["vector_score"]),
            6,
        )
    return results
