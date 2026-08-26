import os
import unittest

from unittest.mock import patch

import httpx

from pilos.collection.ai_clients.reranker_client import (
    AcademyRerankerClient,
    RerankerClientSettings,
)


class FakePost:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, **arguments):
        self.calls.append((url, arguments))
        payload = self.responses.pop(0)
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json=payload,
            request=request,
        )


class RerankerClientTest(unittest.TestCase):
    def test_query_and_documents_use_academy_embedding_protocol(self):
        post = FakePost(
            [
                {
                    "data": [
                        {
                            "index": 0,
                            "embedding": [
                                [1.0, 0.0, 0.0],
                                [0.5, 0.5, 0.0],
                            ],
                        }
                    ]
                },
                {
                    "data": [
                        {
                            "index": 0,
                            "embedding": [
                                [0.9, 0.1, 0.0],
                            ],
                        },
                        {
                            "index": 1,
                            "embedding": [
                                [0.0, 1.0, 0.0],
                            ],
                        },
                    ]
                },
            ]
        )
        client = AcademyRerankerClient(
            settings=RerankerClientSettings(
                base_url="http://academy.example:8091/v1",
                api_key="EMPTY",
                model="bge-reranker-v2-m3",
                timeout_seconds=120,
            ),
            post=post,
        )

        query_vector = client.encode_query("질문")
        document_vectors = client.encode_documents(
            ["관련 문서", "무관 문서"]
        )

        self.assertEqual(query_vector, [1.0, 0.0, 0.0])
        self.assertEqual(len(document_vectors), 2)
        self.assertEqual(
            post.calls[0][1]["json"],
            {"input": "질문"},
        )
        self.assertEqual(
            post.calls[1][1]["json"],
            {"input": ["관련 문서", "무관 문서"]},
        )

    def test_settings_are_loaded_from_environment(self):
        environment = {
            "RERANK_BASE_URL": "http://academy.example:8091/v1/",
            "RERANK_API_KEY": "EMPTY",
            "RERANK_MODEL": "bge-reranker-v2-m3",
            "RERANK_TIMEOUT_SECONDS": "60",
        }

        with patch.dict(os.environ, environment, clear=False):
            settings = RerankerClientSettings.from_env()

        self.assertEqual(
            settings.base_url,
            "http://academy.example:8091/v1",
        )
        self.assertEqual(settings.model, "bge-reranker-v2-m3")
        self.assertEqual(settings.timeout_seconds, 60)


if __name__ == "__main__":
    unittest.main()
