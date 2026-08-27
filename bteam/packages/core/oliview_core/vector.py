from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from urllib.request import Request, urlopen

CANONICAL_COLLECTION = "oliview_review_sentences_v2"
LEGACY_COLLECTION = "oliview_review_sentences"


def canonical_metadata(
    *,
    source_review_id: int,
    product_id: int,
    aspect_sentence_id: int,
    sentence: str,
    **extra: object,
) -> dict[str, object]:
    metadata = {
        "source_review_id": int(source_review_id),
        "review_id": int(source_review_id),
        "product_id": int(product_id),
        "aspect_sentence_id": int(aspect_sentence_id),
        "sentence": sentence,
    }
    metadata.update(extra)
    return metadata


class ChromaVectorClient:
    """Small dependency-free client for the Chroma v2 HTTP API."""

    def __init__(self, endpoint: str, *, collection: str = CANONICAL_COLLECTION):
        self.endpoint = endpoint.rstrip("/")
        self.collection = collection

    def _request(
        self, method: str, path: str, payload: Mapping[str, object] | None = None
    ) -> object:
        body = (
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None
            else None
        )
        request = Request(
            f"{self.endpoint}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def collection_id(self) -> str:
        collections = self._request(
            "GET",
            "/api/v2/tenants/default_tenant/databases/default_database/collections",
        )
        if not isinstance(collections, list):
            raise TypeError("Chroma collection response must be a list")
        for collection in collections:
            if (
                isinstance(collection, dict)
                and collection.get("name") == self.collection
            ):
                return str(collection["id"])
        raise LookupError(f"Chroma collection not found: {self.collection}")

    def query(
        self,
        embedding: list[float],
        *,
        product_id: int | None = None,
        limit: int = 5,
    ) -> list[dict[str, object]]:
        if not embedding:
            return []
        where: dict[str, object] | None = (
            {"product_id": int(product_id)} if product_id is not None else None
        )
        payload: dict[str, object] = {
            "query_embeddings": [embedding],
            "n_results": limit,
            "include": ["documents", "metadatas"],
        }
        if where is not None:
            payload["where"] = where
        result = self._request(
            "POST",
            f"/api/v2/tenants/default_tenant/databases/default_database/collections/{self.collection_id()}/query",
            payload,
        )
        if not isinstance(result, dict):
            raise TypeError("Chroma query response must be an object")
        ids = result.get("ids") or [[]]
        documents = result.get("documents") or [[]]
        metadatas = result.get("metadatas") or [[]]
        rows: list[dict[str, object]] = []
        for index, value in enumerate(ids[0] if ids else []):
            metadata = metadatas[0][index] if metadatas and metadatas[0] else {}
            metadata = metadata if isinstance(metadata, dict) else {}
            source_id = metadata.get("source_review_id", metadata.get("review_id"))
            row_product_id = metadata.get("product_id")
            document = documents[0][index] if documents and documents[0] else ""
            if source_id is None or row_product_id is None:
                continue
            rows.append(
                {
                    "id": str(value),
                    "source_review_id": int(source_id),
                    "product_id": int(row_product_id),
                    "text": str(document or ""),
                    "metadata": metadata,
                }
            )
        return rows

    def upsert(
        self,
        *,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: Sequence[Mapping[str, object]],
        max_attempts: int = 3,
    ) -> object:
        """Upsert one bounded v2 batch with exponential retry backoff."""
        if not ids:
            return None
        if not (
            len(ids) == len(embeddings) == len(documents) == len(metadatas)
        ):
            raise ValueError("Chroma upsert fields must have equal lengths")
        payload: dict[str, object] = {
            "ids": ids,
            "embeddings": embeddings,
            "documents": documents,
            "metadatas": [dict(metadata) for metadata in metadatas],
        }
        last_error: Exception | None = None
        path = (
            "/api/v2/tenants/default_tenant/databases/default_database/collections/"
            f"{self.collection_id()}/upsert"
        )
        for attempt in range(1, max_attempts + 1):
            try:
                return self._request("POST", path, payload)
            except (OSError, TypeError, ValueError) as error:
                last_error = error
                if attempt == max_attempts:
                    break
                time.sleep(min(4.0, 0.5 * (2 ** (attempt - 1))))
        raise RuntimeError("Chroma v2 upsert failed after bounded retries") from last_error
