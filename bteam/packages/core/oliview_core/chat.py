"""Shared ChatA/ChatB compatibility adapter.

It keeps the legacy node order visible in the event stream while using the
Green Core contracts for retrieval, grounding, PII masking, and sessions.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterable, Mapping
from typing import Any, cast

from .guardrails.pii_filter import mask_pii
from .guardrails.sanitizer import normalize_quote
from .rag import RetrievalDocument, grounded_response
from .retrieval import hybrid_retrieve
from .session import InMemorySessionStore, RedisSessionStore
from .vector import ChromaVectorClient


def _as_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


ReviewLookup = Callable[[list[int]], Mapping[int | str, Mapping[str, object]]]


class MySQLReviewLookup:
    """Read-only review lookup used to validate chatbot citations."""

    def __init__(self) -> None:
        self._engine: object | None = None

    def __call__(self, review_ids: list[int]) -> Mapping[int, Mapping[str, object]]:
        if not review_ids:
            return {}
        from sqlalchemy import text

        from .db.connection import create_mysql_engine

        if self._engine is None:
            self._engine = create_mysql_engine(pool_size=2)
        placeholders = ", ".join(
            f":review_{index}" for index in range(len(review_ids))
        )
        params = {
            f"review_{index}": review_id
            for index, review_id in enumerate(review_ids)
        }
        statement = text(
            "SELECT review_id, product_id, review_content "
            f"FROM reviews WHERE review_id IN ({placeholders})"
        )
        engine = cast(Any, self._engine)
        with engine.connect() as connection:
            rows = connection.execute(statement, params).mappings().all()
        return {
            int(row["review_id"]): {
                "product_id": row["product_id"],
                "review_content": row["review_content"],
            }
            for row in rows
        }


class ChatEngine:
    stages = (
        ("INTENT_ANALYSIS", "1. 의도 및 대화 맥락 분석"),
        ("HYBRID_SEARCH", "2. 하이브리드 검색"),
        ("RERANKING", "3. 통합 리랭킹"),
        ("LLM_SYNTHESIS", "4. 근거 기반 답변 생성"),
    )

    def __init__(
        self,
        *,
        session_store: InMemorySessionStore | RedisSessionStore | None = None,
        review_lookup: ReviewLookup | None = None,
    ) -> None:
        self.session_store = session_store or RedisSessionStore()
        self.review_lookup: ReviewLookup | None = review_lookup
        if self.review_lookup is None and os.getenv("MYSQL_USER") and os.getenv(
            "MYSQL_PASSWORD"
        ):
            self.review_lookup = cast(ReviewLookup, MySQLReviewLookup())

    @staticmethod
    def _parse_documents(payload: Mapping[str, object]) -> list[RetrievalDocument]:
        raw_documents = payload.get("documents", [])
        if not isinstance(raw_documents, list):
            return []
        documents: list[RetrievalDocument] = []
        for item in raw_documents:
            if not isinstance(item, Mapping):
                continue
            source_review_id = _as_int(
                item.get("source_review_id", item.get("review_id"))
            )
            item_product_id = _as_int(item.get("product_id"))
            if source_review_id is None or item_product_id is None:
                continue
            metadata = item.get("metadata", {})
            metadata_dict = (
                dict(cast(Mapping[str, object], metadata))
                if isinstance(metadata, Mapping)
                else {}
            )
            documents.append(
                RetrievalDocument(
                    source_review_id,
                    item_product_id,
                    str(item.get("text", item.get("separated_sentence", ""))),
                    metadata=metadata_dict,
                )
            )
        return documents

    @staticmethod
    def _vector_rows(payload: Mapping[str, object]) -> list[dict[str, object]]:
        embedding = payload.get("query_embedding")
        if not isinstance(embedding, list) or not embedding:
            return []
        endpoint = os.getenv("CHROMA_READ_ENDPOINT") or os.getenv(
            "CHROMA_WRITE_ENDPOINT", ""
        )
        if not endpoint:
            return []
        product_id = _as_int(payload.get("product_id"))
        try:
            return ChromaVectorClient(endpoint).query(
                [float(value) for value in embedding],
                product_id=product_id,
                limit=max(1, min(50, _as_int(payload.get("limit", 6)) or 6)),
            )
        except (OSError, LookupError, TypeError, ValueError):
            return []

    def respond(
        self,
        payload: Mapping[str, object],
        *,
        service: str,
        trace_id: str | None = None,
    ) -> dict[str, object]:
        trace = trace_id or uuid.uuid4().hex
        query = str(payload.get("query", "")).strip()
        session_id = str(payload.get("session_id") or f"sess_{trace}")
        product_id = _as_int(payload.get("product_id"))
        safe_query = mask_pii(query)

        if query:
            self.session_store.append_message(session_id, "user", safe_query)

        documents = self._parse_documents(payload)
        # Accept both inputs when a caller has a lexical candidate cache and a
        # vector embedding.  The retriever deduplicates by source review ID and
        # combines the two rankings instead of silently choosing one path.
        vector_rows = self._vector_rows(payload)
        ranked = hybrid_retrieve(
            query,
            documents,
            vector_rows,
            product_id=product_id,
            limit=max(1, min(50, _as_int(payload.get("limit", 6)) or 6)),
        )
        grounding_failed = False
        if ranked and self.review_lookup is not None:
            try:
                review_ids = [
                    review_id
                    for row in ranked
                    if (review_id := _as_int(row.get("source_review_id"))) is not None
                ]
                reviews = self.review_lookup(review_ids)
                validated: list[dict[str, object]] = []
                for row in ranked:
                    review_id = _as_int(row.get("source_review_id"))
                    if review_id is None:
                        continue
                    review = reviews.get(review_id)
                    if review is None:
                        review = reviews.get(str(review_id))
                    if review is None:
                        continue
                    if str(review.get("product_id")) != str(row["product_id"]):
                        continue
                    source = mask_pii(str(review.get("review_content", "")))
                    quote = normalize_quote(str(row["text"]))
                    if quote and quote.casefold() not in normalize_quote(source).casefold():
                        continue
                    validated.append(row)
                grounding_failed = not validated
                ranked = validated
            except Exception:  # noqa: BLE001 - citation validation must fail closed
                grounding_failed = True
                ranked = []
        grounded_documents = [
            RetrievalDocument(
                _as_int(row.get("source_review_id")) or 0,
                _as_int(row.get("product_id")) or 0,
                str(row["text"]),
                metadata=(
                    dict(cast(Mapping[str, object], row.get("metadata")))
                    if isinstance(row.get("metadata"), Mapping)
                    else {}
                ),
            )
            for row in ranked
        ]
        response = grounded_response(
            safe_query,
            grounded_documents,
            product_id=product_id,
            abstention_reason=(
                "GROUNDING_FAILED" if grounding_failed else "NO_CITABLE_SOURCE"
            ),
        )
        response.update(
            {
                "service": service,
                "trace_id": trace,
                "session_id": session_id,
                "stages": [stage_id for stage_id, _ in self.stages],
                "retrieved_documents": [
                    {
                        "source_review_id": row["source_review_id"],
                        "product_id": row["product_id"],
                        "text": row["text"],
                        "rank": row["rank"],
                        "retrieval_score": row["retrieval_score"],
                        "rerank_score": row["rerank_score"],
                    }
                    for row in ranked
                ],
            }
        )
        self.session_store.append_message(
            session_id, "assistant", str(response["answer"])
        )
        return response

    def stream(
        self,
        payload: Mapping[str, object],
        *,
        service: str,
        trace_id: str | None = None,
    ) -> Iterable[dict[str, object]]:
        trace = trace_id or uuid.uuid4().hex
        response = self.respond(payload, service=service, trace_id=trace)
        for stage_id, label in self.stages:
            yield {
                "event_type": "step_update",
                "step_id": stage_id,
                "phase": stage_id,
                "step_name": label,
                "status": "complete",
                "trace_id": trace,
            }
        if response["status"] == "abstained":
            yield {
                "event_type": "step_update",
                "step_id": "ABSTENTION",
                "phase": "ABSTENTION",
                "step_name": "검색 근거 없음: 사실 주장을 생성하지 않음",
                "status": "complete",
                "trace_id": trace,
            }
        answer = str(response["answer"])
        for start in range(0, len(answer), 48):
            yield {
                "event_type": "token",
                "token": answer[start : start + 48],
                "trace_id": trace,
            }
        yield {"event_type": "complete", **response}
