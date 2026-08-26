"""BGE-M3 벡터와 원문 청크를 로컬 ChromaDB에 저장하고 검색한다."""

import math

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import chromadb

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CHROMA_DIRECTORY = (
    PROJECT_ROOT
    / "artifacts"
    / "rag_chroma"
)
COLLECTION_NAME = "pilos_service_knowledge"
EMBEDDING_DIMENSION = 1024

MetadataValue = str | int | float | bool

REQUIRED_METADATA_FIELDS = {
    "source_label",
    "document_version",
    "chunk_index",
    "status",
}

def get_vector_collection(*,persist_directory: str|Path=DEFAULT_CHROMA_DIRECTORY,) -> Any:
    """로컬에 저장되는 PILOS 지식 Vector collection을 반환한다."""

    chroma_path = Path(persist_directory)
    chroma_path.mkdir(
        parents=True,
        exist_ok=True
    )

    client = chromadb.PersistentClient(
        path=str(chroma_path),
    )

    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=None,
        configuration={"hnsw" : {"space": "cosine",}}
    )

def upsert_vector_chunks(*,
                        chunk_ids: Sequence[str],
                        texts: Sequence[str],
                        embeddings: Sequence[Sequence[float]],
                        metadatas: Sequence[Mapping[str, MetadataValue]],
                        persist_directory: str| Path=DEFAULT_CHROMA_DIRECTORY,
) -> int:
    """청크 원문, BGE-M3 벡터와 출처 정보를 ChromaDB에 저장한다."""

    normalized_ids = _normalize_chunk_ids(chunk_ids)
    normalized_texts = _normalize_texts(texts)
    normalized_embeddings = _normalize_embeddings(embeddings)
    normalized_metadatas = _normalize_metadatas(metadatas)

    record_count = len(normalized_ids)

    if not (
        len(normalized_texts)
        == len(normalized_embeddings)
        == len(normalized_metadatas)
        == record_count
    ):
        raise ValueError(
            "chunk_ids, texts, embeddings, metadatas의 "
            "개수가 모두 같아야 합니다.")

    collection = get_vector_collection(
        persist_directory=persist_directory
    )

    collection.upsert(
        ids=normalized_ids,
        documents=normalized_texts,
        embeddings=normalized_embeddings,
        metadatas=normalized_metadatas
    )
    return record_count

def _completed_version_filter(
    document_version: str,
) -> dict[str, object]:
    cleaned_version = document_version.strip()

    if not cleaned_version:
        raise ValueError(
            "document_version은 비어 있을 수 없습니다."
        )

    return {
        "$and": [
            {
                "status": {
                    "$eq": "completed",
                },
            },
            {
                "document_version": {
                    "$eq": cleaned_version,
                },
            },
        ],
    }

def search_vector_chunks(
    *,
    query_embedding: Sequence[float],
    document_version: str,
    top_k: int = 10,
    persist_directory: str | Path = DEFAULT_CHROMA_DIRECTORY,
) -> list[dict[str, Any]]:
    """질문 벡터와 의미가 가까운 완료 상태 청크를 검색한다."""

    if top_k <= 0:
        raise ValueError("top_k는 1 이상이어야 합니다.")

    normalized_query = _normalize_vector(
        query_embedding,
    )

    collection = get_vector_collection(
        persist_directory=persist_directory
    )

    record_count = collection.count()

    if record_count == 0:
        return []

    result = collection.query(
        query_embeddings=[normalized_query],
        n_results=min(top_k, record_count),
        where=_completed_version_filter(
            document_version
        ),
        include=["documents", "metadatas", "distances"],
    )

    ids = result["ids"][0]
    documents = result["documents"][0]
    metadatas = result["metadatas"][0]
    distances = result["distances"][0]

    return [
        {
            "chunk_id": chunk_id,
            "text": document,
            "metadata": metadata,
            "distance": float(distance),
        }
        for chunk_id, document, metadata, distance in zip(
            ids,
            documents,
            metadatas,
            distances,
            strict=True,
        )
    ]

def load_completed_chunks(
    *,
    document_version: str,
    persist_directory: str | Path = DEFAULT_CHROMA_DIRECTORY,
) -> list[dict[str, Any]]:
    """ChromaDB에서 완료 상태 원문 청크 전체를 읽는다."""

    collection = get_vector_collection(
        persist_directory=persist_directory,
    )

    result = collection.get(
        where=_completed_version_filter(
            document_version
        ),
        include=[
            "documents",
            "metadatas",
        ],
    )

    chunk_ids = result.get("ids") or []
    documents = result.get("documents") or []
    metadatas = result.get("metadatas") or []

    if not (
        len(chunk_ids)
        == len(documents)
        == len(metadatas)
    ):
        raise RuntimeError(
            "ChromaDB 청크 ID, 원문, metadata 개수가 다릅니다."
        )

    chunks = []

    for chunk_id, document, metadata in zip(
        chunk_ids,
        documents,
        metadatas,
        strict=True,
    ):
        if (not isinstance(chunk_id, str) or not chunk_id.strip()):
            raise RuntimeError("ChromaDB에 올바르지 않은 chunk_id가 있습니다.")

        if (not isinstance(document, str) or not document.strip()):
            raise RuntimeError("ChromaDB에 빈 청크 원문이 있습니다.")

        if not isinstance(metadata, Mapping):
            raise RuntimeError("ChromaDB 청크 metadata가 올바르지 않습니다.")

        if metadata.get("status") != "completed":
            raise RuntimeError("완료 상태가 아닌 청크가 조회됐습니다.")

        chunks.append(
            {
                "chunk_id": chunk_id.strip(),
                "text": document.strip(),
                "metadata": dict(metadata),
            }
        )

    chunks.sort(
        key=lambda chunk: (
            str(
                chunk["metadata"].get(
                    "source_label",
                    "",
                )
            ),
            str(
                chunk["metadata"].get(
                    "document_version",
                    "",
                )
            ),
            int(
                chunk["metadata"].get(
                    "chunk_index",
                    0,
                )
            ),
            chunk["chunk_id"],
        )
    )

    return chunks


### 전처리 함수

def _normalize_chunk_ids(chunk_ids: Sequence[str],) -> list[str]:
    """청크 ID가 비어 있거나 중복되지 않았는지 확인한다."""

    if isinstance(chunk_ids, (str, bytes)):
        raise TypeError("chunk_ids는 문자열 목록이어야 합니다.")

    normalized = []

    for chunk_id in chunk_ids:
        if not isinstance(chunk_id, str):
            raise TypeError("청크 ID는 문자열이어야 합니다.")

        cleaned = chunk_id.strip()

        if not cleaned:
            raise ValueError("청크 ID는 비어 있을 수 없습니다.")

        normalized.append(cleaned)

    if not normalized:
        raise ValueError("저장할 청크가 한 개 이상 필요합니다.")

    if len(set(normalized)) != len(normalized):
        raise ValueError("같은 요청에 중복된 청크 ID가 있습니다.")

    return normalized


def _normalize_texts(texts: Sequence[str],) -> list[str]:
    """빈 원문 청크가 저장되지 않도록 확인한다."""
    if isinstance(texts, (str, bytes)):
        raise TypeError("texts는 문자열 목록이어야 합니다.")

    normalized = []

    for text in texts:
        if not isinstance(text, str):
            raise TypeError("청크 원문은 문자열이어야 합니다.")

        cleaned = text.strip()

        if not cleaned:
            raise ValueError("빈 청크 원문은 저장할 수 없습니다.")

        normalized.append(cleaned)

    return normalized

def _normalize_embeddings(embeddings: Sequence[Sequence[float]],) -> list[list[float]]:
    """모든 문서 벡터가 1024차원인지 확인한다."""

    return [
        _normalize_vector(embedding)
        for embedding in embeddings
    ]

def _normalize_vector(vector: Sequence[float],) -> list[float]:
    """벡터를 실수 목록으로 변환하고 차원을 확인한다."""
    if isinstance(vector, (str, bytes)):
        raise TypeError("Embedding 벡터는 숫자 목록이어야 합니다.")

    normalized = [float(value)for value in vector]

    if len(normalized) != EMBEDDING_DIMENSION:
        raise ValueError("BGE-M3 Embedding 벡터는 "
            f"{EMBEDDING_DIMENSION}차원이어야 합니다."
        )

    if not all(
        math.isfinite(value)
        for value in normalized):
        
        raise ValueError("Embedding 벡터에 유효하지 않은 숫자가 있습니다.")

    return normalized


def _normalize_metadatas(metadatas: Sequence[Mapping[str, MetadataValue]],) -> list[dict[str, MetadataValue]]:
    """검색 결과에 필요한 출처 정보가 있는지 확인한다."""
    normalized = []

    for metadata in metadatas:
        missing = (REQUIRED_METADATA_FIELDS- set(metadata))
        if missing:
            raise ValueError(
                "필수 청크 metadata가 없습니다: "
                f"{sorted(missing)}")

        if metadata["status"] != "completed":
            raise ValueError("완료 상태 청크만 Vector DB에 저장할 수 있습니다.")
        normalized.append(dict(metadata))

    return normalized
