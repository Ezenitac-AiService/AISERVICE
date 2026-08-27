from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from oliview_core.cache.redis_manager import CacheVersionManager
from oliview_core.vector import CANONICAL_COLLECTION, canonical_metadata


@dataclass(frozen=True)
class IndexDocument:
    aspect_sentence_id: int
    source_review_id: int
    product_id: int
    sentence: str


def to_v2_upsert(document: IndexDocument) -> tuple[str, dict[str, object]]:
    return str(document.aspect_sentence_id), canonical_metadata(
        source_review_id=document.source_review_id,
        product_id=document.product_id,
        aspect_sentence_id=document.aspect_sentence_id,
        sentence=document.sentence,
    )


def prepare_batch(
    documents: Iterable[IndexDocument],
) -> list[tuple[str, dict[str, object]]]:
    return [to_v2_upsert(document) for document in documents]


class IncrementalIndexer:
    def __init__(
        self,
        upsert: Callable[[str, list[dict[str, object]], list[str]], None],
        *,
        max_attempts: int = 3,
    ):
        self.upsert = upsert
        self.max_attempts = max_attempts
        self.checkpoints: dict[str, int] = {CANONICAL_COLLECTION: 0}
        self.pending: list[IndexDocument] = []

    def index(
        self,
        documents: Iterable[IndexDocument],
        *,
        product_id: int | None = None,
        cache_manager: CacheVersionManager | None = None,
    ) -> int:
        rows = list(documents)
        if not rows:
            return 0
        ids: list[str] = []
        metadata: list[dict[str, object]] = []
        for document in rows:
            identifier, item = to_v2_upsert(document)
            ids.append(identifier)
            metadata.append(item)
        last_error: Exception | None = None
        for _attempt in range(1, self.max_attempts + 1):
            try:
                self.upsert(CANONICAL_COLLECTION, metadata, ids)
                self.checkpoints[CANONICAL_COLLECTION] += len(rows)
                if cache_manager is not None and product_id is not None:
                    cache_manager.bump(product_id, "rag")
                return len(rows)
            except Exception as error:  # noqa: BLE001 - bounded retry boundary
                last_error = error
        self.pending.extend(rows)
        raise RuntimeError(
            "Chroma v2 upsert failed after bounded retries"
        ) from last_error
