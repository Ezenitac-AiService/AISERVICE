"""BM25와 Vector 검색 순위를 RRF 방식으로 결합한다."""

from collections.abc import Mapping, Sequence
from typing import Any


DEFAULT_RRF_K = 60
DEFAULT_TOP_K = 10

def reciprocal_rank_fusion(
    bm25_results: Sequence[Mapping[str, Any]],
    vector_results: Sequence[Mapping[str, Any]],
    *,
    rrf_k: int = DEFAULT_RRF_K,
    top_k: int = DEFAULT_TOP_K,
)-> list[dict[str, Any]]:
    """BM25와 Vector 검색 순위를 하나의 RRF 순위로 합친다."""

    if rrf_k <= 0:
        raise ValueError("rrf_k는 1 이상이어야 합니다.")

    if top_k <= 0:
        raise ValueError("top_k는 1 이상이어야 합니다.")

    candidates: dict[str, dict[str, Any]] = {}

    _add_ranked_results(
        candidates=candidates,
        results=bm25_results,
        search_type="bm25",
        rrf_k=rrf_k,
    )

    _add_ranked_results(
        candidates=candidates,
        results=vector_results,
        search_type="vector",
        rrf_k=rrf_k,
    )

    fused_results = list(candidates.values())

    fused_results.sort(
        key=lambda item: (
            -item["rrf_score"],
            _best_rank(item),
            item["chunk_id"],
        )
    )

    return fused_results[:top_k]

def _add_ranked_results(
    *,
    candidates: dict[str, dict[str, Any]],
    results: Sequence[Mapping[str, Any]],
    search_type: str,
    rrf_k: int,
) -> None:
    """한 검색기의 순위 점수를 전체 RRF 후보에 더한다."""

    if search_type not in {"bm25", "vector"}:
        raise ValueError(
            "search_type은 bm25 또는 vector여야 합니다."
        )

    seen_chunk_ids = set()

    for rank, result in enumerate(
        results,
        start=1,
    ):
        chunk_id = result.get("chunk_id")
        text = result.get("text")
        metadata = result.get("metadata")

        if (
            not isinstance(chunk_id, str)
            or not chunk_id.strip()
        ):
            raise ValueError(
                "검색 결과의 chunk_id가 올바르지 않습니다."
            )

        chunk_id = chunk_id.strip()

        if chunk_id in seen_chunk_ids:
            raise ValueError(
                f"{search_type} 검색 결과에 "
                f"중복된 chunk_id가 있습니다: {chunk_id}"
            )

        if (
            not isinstance(text, str)
            or not text.strip()
        ):
            raise ValueError(
                "검색 결과의 text가 올바르지 않습니다."
            )

        if not isinstance(metadata, Mapping):
            raise TypeError(
                "검색 결과의 metadata는 mapping이어야 합니다."
            )

        seen_chunk_ids.add(chunk_id)

        if chunk_id not in candidates:
            candidates[chunk_id] = {
                "chunk_id": chunk_id,
                "text": text.strip(),
                "metadata": dict(metadata),
                "bm25_rank": None,
                "bm25_score": None,
                "vector_rank": None,
                "vector_distance": None,
                "rrf_score": 0.0,
            }
        else:
            candidate = candidates[chunk_id]

            if candidate["text"] != text.strip():
                raise ValueError(
                    "같은 chunk_id의 원문 text가 "
                    f"검색기마다 다릅니다: {chunk_id}"
                )

        candidate = candidates[chunk_id]

        candidate["rrf_score"] += (
            1.0 / (rrf_k + rank)
        )

        if search_type == "bm25":
            candidate["bm25_rank"] = rank
            candidate["bm25_score"] = result.get(
                "bm25_score"
            )
        else:
            candidate["vector_rank"] = rank
            candidate["vector_distance"] = result.get(
                "distance"
            )


def _best_rank(
    result: Mapping[str, Any],
) -> int:
    """BM25와 Vector 순위 중 가장 높은 순위를 반환한다."""

    ranks = [
        rank
        for rank in (
            result.get("bm25_rank"),
            result.get("vector_rank"),
        )
        if isinstance(rank, int)
    ]

    if not ranks:
        return 999_999

    return min(ranks)
