"""학원 Reranker 벡터의 cosine 유사도로 RRF 후보를 재정렬한다."""

import math

from collections.abc import Mapping, Sequence
from typing import Any


DEFAULT_RERANK_TOP_K = 5


def rerank_chunks(
    chunks: Sequence[Mapping[str, Any]],
    *,
    query_vector: Sequence[float],
    document_vectors: Sequence[Sequence[float]],
    top_k: int = DEFAULT_RERANK_TOP_K,
) -> list[dict[str, Any]]:
    """질문·문서 벡터의 cosine 점수로 후보 청크를 재정렬한다."""
    if not chunks:
        return []

    if top_k <= 0:
        raise ValueError(
            "top_k는 1 이상이어야 합니다."
        )

    if len(chunks) != len(document_vectors):
        raise ValueError(
            "Rerank 청크와 문서 벡터 개수가 다릅니다."
        )

    normalized_query_vector = _normalize_vector(
        query_vector,
        field_name="query_vector",
    )
    normalized_chunks = _normalize_chunks(chunks)
    reranked_results: list[dict[str, Any]] = []

    for chunk, document_vector in zip(
        normalized_chunks,
        document_vectors,
        strict=True,
    ):
        normalized_document_vector = _normalize_vector(
            document_vector,
            field_name="document_vector",
        )

        if len(normalized_query_vector) != len(
            normalized_document_vector
        ):
            raise ValueError(
                "질문 벡터와 문서 벡터 차원이 다릅니다."
            )

        result = dict(chunk)
        result["rerank_score"] = _cosine_similarity(
            normalized_query_vector,
            normalized_document_vector,
        )
        reranked_results.append(result)

    reranked_results.sort(
        key=lambda result: (
            -result["rerank_score"],
            -result.get("rrf_score", 0.0),
            result["chunk_id"],
        )
    )

    for rank, result in enumerate(
        reranked_results,
        start=1,
    ):
        result["rerank_rank"] = rank

    return reranked_results[:top_k]


def _cosine_similarity(
    first: Sequence[float],
    second: Sequence[float],
) -> float:
    dot_product = sum(
        left * right
        for left, right in zip(first, second, strict=True)
    )
    first_norm = math.sqrt(
        sum(value * value for value in first)
    )
    second_norm = math.sqrt(
        sum(value * value for value in second)
    )

    if first_norm == 0 or second_norm == 0:
        return 0.0

    return dot_product / (first_norm * second_norm)


def _normalize_vector(
    vector: Sequence[float],
    *,
    field_name: str,
) -> list[float]:
    if isinstance(vector, (str, bytes)) or not vector:
        raise ValueError(
            f"{field_name}는 비어 있지 않은 숫자 목록이어야 합니다."
        )

    try:
        normalized = [float(value) for value in vector]
    except (TypeError, ValueError):
        raise TypeError(
            f"{field_name}에는 숫자만 들어 있어야 합니다."
        ) from None

    if not all(math.isfinite(value) for value in normalized):
        raise ValueError(
            f"{field_name}에 유한하지 않은 값이 있습니다."
        )

    return normalized


def _normalize_chunks(
    chunks: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen_chunk_ids: set[str] = set()

    for chunk in chunks:
        chunk_id = chunk.get("chunk_id")
        text = chunk.get("text")
        metadata = chunk.get("metadata")
        rrf_score = chunk.get("rrf_score")

        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise ValueError(
                "Rerank 청크의 chunk_id가 올바르지 않습니다."
            )

        cleaned_chunk_id = chunk_id.strip()

        if cleaned_chunk_id in seen_chunk_ids:
            raise ValueError(
                f"중복된 chunk_id입니다: {cleaned_chunk_id}"
            )

        if not isinstance(text, str) or not text.strip():
            raise ValueError(
                "Rerank 청크의 text가 올바르지 않습니다."
            )

        if not isinstance(metadata, Mapping):
            raise TypeError(
                "Rerank 청크의 metadata는 mapping이어야 합니다."
            )

        if not isinstance(rrf_score, (int, float)):
            raise TypeError(
                "Rerank 청크의 rrf_score는 숫자여야 합니다."
            )

        seen_chunk_ids.add(cleaned_chunk_id)
        normalized.append(
            {
                **dict(chunk),
                "chunk_id": cleaned_chunk_id,
                "text": text.strip(),
                "metadata": dict(metadata),
                "rrf_score": float(rrf_score),
            }
        )

    return normalized
