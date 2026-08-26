import math
import os
import unittest

from pilos.collection.ai_clients.embedding_client import (
    EMBEDDING_DIMENSION,
    EmbeddingClientSettings,
    OpenAICompatibleEmbeddingClient,
)
from pilos.collection.ai_clients.reranker_client import (
    AcademyRerankerClient,
    RerankerClientSettings,
)
from pilos.storage.vector_storage import load_completed_chunks
from pilos.web.app import app


_RUN_RAG_E2E = (
    os.environ.get("RUN_RAG_E2E", "")
    .strip()
    .lower()
    in {"1", "true", "yes", "on"}
)

_E2E_QUERY = "model_date는 무슨 날짜야?"


@unittest.skipUnless(
    _RUN_RAG_E2E,
    "RUN_RAG_E2E=1일 때만 실제 RAG E2E를 실행합니다.",
)
class ChatbotRagE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document_version = os.environ.get(
            "SERVICE_KNOWLEDGE_VERSION",
            "",
        ).strip()

        if not cls.document_version:
            raise RuntimeError(
                "SERVICE_KNOWLEDGE_VERSION이 필요합니다."
            )

        cls.completed_chunks = load_completed_chunks(
            document_version=cls.document_version,
        )

    def test_active_chroma_version_has_completed_chunks(
        self,
    ):
        self.assertTrue(
            self.completed_chunks,
            "활성 버전의 Chroma 청크가 없습니다.",
        )

        for chunk in self.completed_chunks:
            with self.subTest(
                chunk_id=chunk["chunk_id"],
            ):
                metadata = chunk["metadata"]

                self.assertEqual(
                    metadata.get("status"),
                    "completed",
                )
                self.assertEqual(
                    metadata.get("document_version"),
                    self.document_version,
                )
                self.assertTrue(
                    chunk["text"].strip()
                )

    def test_embedding_server_returns_1024_dimensions(
        self,
    ):
        client = OpenAICompatibleEmbeddingClient(
            settings=EmbeddingClientSettings.from_env(),
        )

        embedding = client.embed_query(_E2E_QUERY)

        self.assertEqual(
            len(embedding),
            EMBEDDING_DIMENSION,
        )
        self.assertTrue(
            all(
                math.isfinite(value)
                for value in embedding
            )
        )

    def test_reranker_server_returns_compatible_vectors(
        self,
    ):
        client = AcademyRerankerClient(
            settings=RerankerClientSettings.from_env(),
        )

        query_vector = client.encode_query(
            _E2E_QUERY,
        )
        document_vectors = client.encode_documents(
            [
                self.completed_chunks[0]["text"],
            ]
        )

        self.assertTrue(query_vector)
        self.assertEqual(
            len(document_vectors),
            1,
        )
        self.assertEqual(
            len(query_vector),
            len(document_vectors[0]),
        )
        self.assertTrue(
            all(
                math.isfinite(value)
                for value in query_vector
            )
        )
        self.assertTrue(
            all(
                math.isfinite(value)
                for value in document_vectors[0]
            )
        )

    def test_chat_api_completes_real_rag_flow(
        self,
    ):
        app.config["TESTING"] = True
        client = app.test_client()

        response = client.post(
            "/api/chat",
            json={
                "action": "service_knowledge",
                "message": _E2E_QUERY,
                "session_id": "rag-e2e-session",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        body = response.get_json()

        self.assertEqual(
            body["status"],
            "ready",
        )
        self.assertEqual(
            body["route"],
            "service_knowledge",
        )
        self.assertEqual(
            body["session_id"],
            "rag-e2e-session",
        )
        self.assertTrue(
            body["answer"].strip()
        )
        self.assertTrue(
            body["sources"]
        )

        for source in body["sources"]:
            with self.subTest(
                label=source["label"],
            ):
                self.assertEqual(
                    source["type"],
                    "service_document",
                )
                self.assertEqual(
                    source["version"],
                    self.document_version,
                )

        public_response = str(body)

        self.assertNotIn(
            "chunk_id",
            public_response,
        )
        self.assertNotIn(
            "rerank_score",
            public_response,
        )
        self.assertNotIn(
            "distance",
            public_response,
        )
        self.assertNotIn(
            "API_KEY",
            public_response,
        )


if __name__ == "__main__":
    unittest.main()
