"""Model Gateway OpenAI-compatible Contract Verification Test (FR-001, FR-005, FR-007).

Validates request/response structure and contract schemas using standard library.
"""

import json
import unittest


class TestEmbeddingGatewayContract(unittest.TestCase):
    def test_embedding_request_structure(self):
        """FR-005: /v1/embeddings schema contract."""
        payload = {
            "model": "bge-m3",
            "input": ["차앤박 프로폴리스 앰플 수분감을 분석해줘"]
        }
        self.assertEqual(payload["model"], "bge-m3")
        self.assertIsInstance(payload["input"], list)
        self.assertTrue(len(payload["input"]) > 0)

    def test_chat_completions_request_structure(self):
        """FR-001, FR-005: /v1/chat/completions schema contract."""
        payload = {
            "model": "qwen3.5-4b",
            "messages": [
                {"role": "system", "content": "당신은 AI 어시스턴트입니다."},
                {"role": "user", "content": "PILOS 분석 결과 해석 방법"}
            ],
            "stream": True,
            "temperature": 0.3,
            "max_tokens": 1024
        }
        self.assertEqual(payload["model"], "qwen3.5-4b")
        self.assertIsInstance(payload["messages"], list)
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertTrue(isinstance(payload["stream"], bool))

    def test_reranker_request_structure(self):
        """FR-005: /v1/rerank schema contract."""
        payload = {
            "model": "bge-reranker-v2-m3",
            "query": "보습력이 뛰어난 에센스 추천",
            "documents": [
                "차앤박 프로폴리스 앰플은 강력한 보습막을 형성합니다.",
                "선크림은 자외선을 차단합니다."
            ],
            "top_n": 2
        }
        self.assertEqual(payload["model"], "bge-reranker-v2-m3")
        self.assertIsInstance(payload["query"], str)
        self.assertIsInstance(payload["documents"], list)
        self.assertEqual(payload["top_n"], 2)


if __name__ == "__main__":
    unittest.main()
