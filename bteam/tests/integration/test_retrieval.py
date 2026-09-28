"""
Integration tests for Lock-Free Chroma Server mode and MySQL fallback in HybridRetriever.
Feature: 008-bteam-rag-refactor
"""

import pytest
import chromadb
from unittest.mock import patch, MagicMock

from oliview_core.config import CoreSettings, get_settings
from oliview_core.client import AiGatewayClient
from oliview_core.retrieval import HybridRetriever


@pytest.fixture
def local_settings():
    return CoreSettings(
        CHROMA_SERVER_HOST="127.0.0.1",
        CHROMA_SERVER_PORT=8000,
        EMBEDDING_BASE_URL="http://127.0.0.1:8081/v1",
        RERANK_BASE_URL="http://127.0.0.1:8081/v1",
        LLM_BASE_URL="http://127.0.0.1:8081/v1",
    )


def test_chroma_server_connection(local_settings: CoreSettings):
    """Verify live Chroma server at 127.0.0.1:8000 exposes oliview_review_sentences collection."""
    client = chromadb.HttpClient(host=local_settings.chroma_server_host, port=local_settings.chroma_server_port)
    cols = client.list_collections()
    col_names = [c.name for c in cols]
    assert "oliview_review_sentences" in col_names
    col = client.get_collection("oliview_review_sentences")
    count = col.count()
    assert count >= 50000, f"Expected >= 50000 review vectors, got {count}"


def test_hybrid_retriever_chroma_server_mode(local_settings: CoreSettings):
    """Verify HybridRetriever connects via HttpClient and retrieves vectors without SQLite file locking."""
    with patch("oliview_core.retrieval.get_settings", return_value=local_settings):
        ai_client = AiGatewayClient(settings=local_settings)
        retriever = HybridRetriever(client=ai_client)

        assert retriever.collection is not None
        # Must not load 5000 documents into local memory
        assert len(retriever.all_documents) == 0

        # Perform search for a valid cosmetic term
        results = retriever.search("수분감과 흡수력", top_k=5, use_cache=False)
        assert len(results) > 0
        first = results[0]
        assert "clean_text" in first or "review_text" in first
        assert "dense_score" in first
        assert first["dense_score"] > 0.0


def test_hybrid_retriever_mysql_fallback(local_settings: CoreSettings):
    """Verify HybridRetriever gracefully falls back to MySQL when Chroma is unavailable."""
    with patch("oliview_core.retrieval.get_settings", return_value=local_settings):
        ai_client = AiGatewayClient(settings=local_settings)
        retriever = HybridRetriever(client=ai_client)
        # Force collection to None to simulate Chroma server failure
        retriever.collection = None

        results = retriever.search("수분감", top_k=3, use_cache=False)
        # MySQL fallback should return candidates or empty list without raising unhandled exceptions
        assert isinstance(results, list)
