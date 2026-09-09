"""공개 서비스 문서를 청킹하고 ChromaDB 인덱스로 구축한다."""

import argparse
import hashlib
import json

from pathlib import Path
from typing import Any

from pilos.analysis.rag.rag_chunking import split_text_into_chunks
from pilos.collection.ai_clients.embedding_client import (
    EmbeddingClientSettings,
    OpenAICompatibleEmbeddingClient,
)
from pilos.storage.vector_storage import (
    DEFAULT_CHROMA_DIRECTORY,
    upsert_vector_chunks,
)

def build_rag_index(
    *,
    source_path: str | Path,
    source_label: str,
    document_version: str,
    persist_directory: str | Path = DEFAULT_CHROMA_DIRECTORY,
    embedding_client: OpenAICompatibleEmbeddingClient | None = None,
) -> dict[str, Any]:
    """공개 문서 하나를 청킹·Embedding하여 ChromaDB에 저장한다."""

    normalized_source_path = Path(source_path).resolve()
    if not normalized_source_path.is_file():
        raise FileNotFoundError(
            "공개 지식 문서를 찾을 수 없습니다: "
            f"{normalized_source_path}"
        )

    if normalized_source_path.suffix.lower() != ".md":
        raise ValueError("초기 RAG 지식 문서는 Markdown 파일만 지원합니다.")

    cleaned_source_label = source_label.strip()

    if not cleaned_source_label:
        raise ValueError("source_label은 비어 있을 수 없습니다.")

    cleaned_document_version = (document_version.strip())

    if not cleaned_document_version:
        raise ValueError("document_version은 비어 있을 수 없습니다.")

    document_text = normalized_source_path.read_text(
        encoding="utf-8",
    ).strip()

    if not document_text:
        raise ValueError(
            "공개 지식 문서의 내용이 비어 있습니다."
        )

    document_hash = hashlib.sha256(
        document_text.encode("utf-8")
    ).hexdigest()

    chunks = split_text_into_chunks(
        document_text,
    )

    if not chunks:
        raise RuntimeError(
            "공개 지식 문서를 청크로 나누지 못했습니다."
        )

    active_embedding_client = embedding_client

    if active_embedding_client is None:
        active_embedding_client = OpenAICompatibleEmbeddingClient(
            settings=EmbeddingClientSettings.from_env(),
        )

    embeddings = active_embedding_client.embed_documents(
        chunks,
    )

    if len(chunks) != len(embeddings):
        raise RuntimeError(
            "청크 개수와 Embedding 개수가 다릅니다."
        )

    chunk_ids = [
        create_chunk_id(
            source_label=cleaned_source_label,
            document_version=cleaned_document_version,
            document_hash=document_hash,
            chunk_index=chunk_index,
        )
        for chunk_index in range(
            len(chunks)
        )
    ]

    metadatas = [
        {
            "source_label": cleaned_source_label,
            "document_version": cleaned_document_version,
            "document_hash": document_hash,
            "chunk_index": chunk_index,
            "status": "completed",
        }
        for chunk_index in range(
            len(chunks)
        )
    ]

    stored_count = upsert_vector_chunks(
        chunk_ids=chunk_ids,
        texts=chunks,
        embeddings=embeddings,
        metadatas=metadatas,
        persist_directory=persist_directory,
    )

    return {
        "source_label": cleaned_source_label,
        "document_version": cleaned_document_version,
        "document_hash": document_hash,
        "chunk_count": len(chunks),
        "embedding_dimension": len(
            embeddings[0]
        ),
        "stored_count": stored_count,
    }

def create_chunk_id(
    *,
    source_label: str,
    document_version: str,
    document_hash: str,
    chunk_index: int,
) -> str:
    """문서 정보와 순서로 재현 가능한 청크 ID를 만든다."""

    chunk_key = "\n".join(
        [
            source_label,
            document_version,
            document_hash,
            str(chunk_index),
        ]
    )

    return hashlib.sha256(
        chunk_key.encode("utf-8")
    ).hexdigest()


def parse_arguments() -> argparse.Namespace:
    """인덱스 구축 명령어의 입력값을 읽는다."""

    parser = argparse.ArgumentParser(
        description=(
            "공개 PILOS 서비스 문서를 "
            "로컬 RAG 인덱스로 구축합니다."
        )
    )

    parser.add_argument(
        "source_path",
        help="공개 Markdown 문서 경로",
    )

    parser.add_argument(
        "--source-label",
        required=True,
        help="사용자에게 표시할 공개 출처명",
    )

    parser.add_argument(
        "--document-version",
        required=True,
        help="공개 문서 버전",
    )

    return parser.parse_args()


def main() -> None:
    """CLI 입력으로 RAG 인덱스를 구축하고 결과를 출력한다."""

    arguments = parse_arguments()

    summary = build_rag_index(
        source_path=arguments.source_path,
        source_label=arguments.source_label,
        document_version=arguments.document_version,
    )

    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
