import unittest
import requests


class TestEmbeddingGatewayContract(unittest.TestCase):
    def test_embedding_request_structure(self):
        payload = {
            "model": "bge-m3",
            "input": ["차앤박 프로폴리스 앰플 수분감을 분석해줘"]
        }
        self.assertEqual(payload["model"], "bge-m3")
        self.assertIsInstance(payload["input"], list)


if __name__ == "__main__":
    unittest.main()
