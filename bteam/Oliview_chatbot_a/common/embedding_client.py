"""HTTP BGE-M3 Embeddings Client for LangChain & ChromaDB.

Replaces local HuggingFace weights dependency by remotely querying
the Model Gateway (vllm-serv-gateway:8090 / v1/embeddings).
"""

from __future__ import annotations

import logging
import os
from typing import Any, List

import requests
from langchain_core.embeddings import Embeddings

logger = logging.getLogger(__name__)


class HttpBgeM3Embeddings(Embeddings):
    """OpenAI-compatible HTTP Embedding Client for BGE-M3 (Port 8090)."""

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str = "bge-m3",
        timeout: float | None = None,
    ):
        if timeout is None:
            timeout = float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "120.0"))
        if not base_url:
            server_host = os.getenv("SERVER_HOST", "http://vllm-serv-gateway")
            if not server_host.startswith("http://") and not server_host.startswith("https://"):
                server_host = f"http://{server_host}"
            embedding_port = os.getenv("EMBEDDING_PORT", "8090")
            base_url = os.getenv(
                "EMBEDDING_BASE_URL",
                f"{server_host}:{embedding_port}/v1",
            )

        # Normalize URL to end with /v1/embeddings
        clean_base = base_url.rstrip("/")
        if clean_base.endswith("/embeddings"):
            self.endpoint = clean_base
        elif clean_base.endswith("/v1"):
            self.endpoint = f"{clean_base}/embeddings"
        else:
            self.endpoint = f"{clean_base}/v1/embeddings"

        self.model_name = model_name
        self.timeout = timeout
        logger.info(f"HttpBgeM3Embeddings initialized with endpoint: {self.endpoint}")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of documents via HTTP POST."""
        if not texts:
            return []

        payload = {
            "model": self.model_name,
            "input": texts,
        }

        try:
            response = requests.post(
                self.endpoint,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

            # OpenAI embeddings response format: {"data": [{"embedding": [...], "index": 0}, ...]}
            sorted_data = sorted(data["data"], key=lambda x: x.get("index", 0))
            return [item["embedding"] for item in sorted_data]
        except Exception as e:
            logger.error(f"HTTP Embedding failed on {self.endpoint}: {e}")
            raise RuntimeError(
                f"Model Gateway 임베딩 서버({self.endpoint}) 호출 실패: {e}"
            ) from e

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query text."""
        result = self.embed_documents([text])
        if not result:
            raise RuntimeError("임베딩 결과가 비어 있습니다.")
        return result[0]
