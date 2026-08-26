"""Kiwi 형태소 분석과 BM25를 이용해 관련 청크를 검색한다."""

from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Any

from kiwipiepy import Kiwi
from rank_bm25 import BM25Okapi


DEFAULT_TOP_K = 10

@lru_cache(maxsize=1)
def get_rag_kiwi() -> Kiwi:
    """RAG 검색용 Kiwi 형태소 분석기를 한 번만 생성한다."""
    return Kiwi()

def tokenize_kiwi(text: str) -> list[str]:
    """한국어 문장에서 BM25 검색에 사용할 핵심 토큰을 추출한다."""

    if not isinstance(text, str):
        raise TypeError("text는 문자열이어야 합니다.")

    cleaned = text.strip()

    if not cleaned:
        return []

    try:
        tokens = get_rag_kiwi().tokenize(cleaned)

        keywords = [
            token.form.lower()
            for token in tokens
            if (token.tag.startswith("N") or token.tag in {"SL", "SN"})
        ]
    except Exception:
        return cleaned.lower().split()

    if keywords:
        return keywords

    return cleaned.lower().split()

class BM25Retriever:
    """완료된 청크 목록을 대상으로 BM25 키워드 검색을 수행한다."""

    def __init__(
        self,
        chunks: Sequence[Mapping[str, Any]],
    ) -> None:
        self._chunks = self._normalize_chunks(chunks)
        corpus = [chunk["text"] for chunk in self._chunks]
        tokenized_corpus = [tokenize_kiwi(text) for text in corpus]
        self._bm25 = BM25Okapi(tokenized_corpus,)

    def search(self,
               query: str,
               *,
               top_k: int=DEFAULT_TOP_K,
    ) -> list[dict[str, Any]]:
        """질문의 핵심 단어와 관련된 상위 청크를 반환한다."""

        if not isinstance(query, str):
            raise TypeError("query는 문자열이어야 합니다.")

        cleaned_query = query.strip()
        if not cleaned_query:
            return []

        if top_k <= 0:
            raise ValueError("top_k는 1 이상이어야 합니다.")

        query_tokens = tokenize_kiwi(cleaned_query,)

        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens,)
        ranked_indices = sorted(
            range(len(scores)),
            key=lambda index: float(scores[index]),
            reverse=True,
        )
        results = []

        for rank, index in enumerate(ranked_indices[:top_k], start=1):
            chunk = self._chunks[index]
            results.append({
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"],
                "metadata": dict(chunk["metadata"]),
                "bm25_score": float(scores[index]),
                "bm25_rank": rank,
            })
        return results
    @staticmethod
    def _normalize_chunks(chunks: Sequence[Mapping[str, Any]],) -> list[dict[str, Any]]:
        """BM25 인덱스에 필요한 청크 필드를 확인한다."""
        if not chunks:
            raise ValueError("BM25 인덱스를 만들 청크가 필요합니다.")

        normalized = []
        seen_chunk_ids = set()

        for chunk in chunks:
            chunk_id = chunk.get("chunk_id")
            text = chunk.get("text")
            metadata = chunk.get("metadata")

            if (not isinstance(chunk_id, str)
                or not chunk_id.strip()):
                raise ValueError("chunk_id는 비어 있지 않은 문자열이어야 합니다.")

            if chunk_id in seen_chunk_ids:
                raise ValueError(f"중복된 chunk_id입니다: {chunk_id}")
            
            if (not isinstance(text, str)
                or not text.strip()):
                raise ValueError("청크 text는 비어 있지 않은 문자열이어야 합니다.")

            if not isinstance(metadata, Mapping):
                raise TypeError("청크 metadata는 mapping이어야 합니다.")

            if metadata.get("status") != "completed":
                raise ValueError("완료 상태 청크만 BM25에 사용할 수 있습니다.")

            seen_chunk_ids.add(chunk_id)
            normalized.append(
                {
                    "chunk_id": chunk_id.strip(),
                    "text": text.strip(),
                    "metadata": dict(metadata),
                }
            )

        return normalized
