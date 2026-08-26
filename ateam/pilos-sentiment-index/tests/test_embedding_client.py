import os
import unittest

from types import SimpleNamespace
from unittest.mock import patch

from pilos.collection.ai_clients.embedding_client import (
    EMBEDDING_DIMENSION,
    EmbeddingClientSettings,
    EmbeddingResponseError,
    OpenAICompatibleEmbeddingClient,
)


class FakeEmbeddingsApi:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **arguments):
        self.calls.append(arguments)
        return self.response


class EmbeddingClientTest(unittest.TestCase):
    def test_batch_embedding_keeps_input_order(self):
        response = SimpleNamespace(
            data=[
                SimpleNamespace(
                    index=1,
                    embedding=[0.2] * EMBEDDING_DIMENSION,
                ),
                SimpleNamespace(
                    index=0,
                    embedding=[0.1] * EMBEDDING_DIMENSION,
                ),
            ]
        )
        embeddings_api = FakeEmbeddingsApi(response)
        sdk_client = SimpleNamespace(embeddings=embeddings_api)
        settings = EmbeddingClientSettings(
            base_url="http://academy.example:8090/v1",
            api_key="EMPTY",
            model="bge-m3",
            timeout_seconds=120,
        )
        client = OpenAICompatibleEmbeddingClient(
            settings=settings,
            sdk_client=sdk_client,
        )

        vectors = client.embed_documents(["첫 문서", "둘째 문서"])

        self.assertEqual(vectors[0][0], 0.1)
        self.assertEqual(vectors[1][0], 0.2)
        self.assertEqual(
            embeddings_api.calls,
            [
                {
                    "model": "bge-m3",
                    "input": ["첫 문서", "둘째 문서"],
                }
            ],
        )

    def test_wrong_dimension_is_rejected(self):
        response = SimpleNamespace(
            data=[
                SimpleNamespace(
                    index=0,
                    embedding=[0.1] * 3,
                )
            ]
        )
        sdk_client = SimpleNamespace(
            embeddings=FakeEmbeddingsApi(response),
        )
        settings = EmbeddingClientSettings(
            base_url="http://academy.example:8090/v1",
            api_key="EMPTY",
            model="bge-m3",
            timeout_seconds=120,
        )
        client = OpenAICompatibleEmbeddingClient(
            settings=settings,
            sdk_client=sdk_client,
        )

        with self.assertRaises(EmbeddingResponseError):
            client.embed_query("질문")

    def test_settings_are_loaded_from_environment(self):
        environment = {
            "EMBEDDING_BASE_URL": "http://academy.example:8090/v1/",
            "EMBEDDING_API_KEY": "EMPTY",
            "EMBEDDING_MODEL": "bge-m3",
            "EMBEDDING_TIMEOUT_SECONDS": "45",
        }

        with patch.dict(os.environ, environment, clear=False):
            settings = EmbeddingClientSettings.from_env()

        self.assertEqual(
            settings.base_url,
            "http://academy.example:8090/v1",
        )
        self.assertEqual(settings.model, "bge-m3")
        self.assertEqual(settings.timeout_seconds, 45)


if __name__ == "__main__":
    unittest.main()
