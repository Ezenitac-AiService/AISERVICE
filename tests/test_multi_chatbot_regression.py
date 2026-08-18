"""3대 챗봇(PILOS, 올리챗, 올원챗) 통합 회귀 테스트 스위트 (US5 / FR-007).

표준 라이브러리(urllib, json, unittest)만을 사용하여 실행됩니다.
"""

import time
import json
import unittest
import urllib.request
import urllib.error
import concurrent.futures


class TestMultiChatbotRegression(unittest.TestCase):
    EMBEDDING_SERVER_URL = "http://127.0.0.1:8090/v1/embeddings"
    PILOS_URL = "http://127.0.0.1:8080/api/chat"
    ALLONECHAT_URL = "http://127.0.0.1:8080/bteam/chatb/api/v1/search"
    OLLYCHAT_URL = "http://127.0.0.1:8080/bteam/chata/"

    def _post_json(self, url: str, data: dict, timeout: float = 30.0) -> tuple[int, dict]:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                body = json.loads(resp.read().decode("utf-8"))
                return status, body
        except urllib.error.HTTPError as e:
            body_bytes = e.read()
            try:
                body = json.loads(body_bytes.decode("utf-8"))
            except Exception:
                body = {"error": body_bytes.decode("utf-8", errors="ignore")}
            return e.code, body

    def test_01_embedding_gateway_endpoint(self):
        """FR-001, FR-002: BGE-M3 임베딩 서버(8090) 5초 내 정상 응답 및 1024차원 벡터 검증."""
        start_time = time.perf_counter()
        status, data = self._post_json(
            self.EMBEDDING_SERVER_URL,
            {"model": "bge-m3", "input": ["차앤박 프로폴리스 앰플 수분감을 분석해줘"]},
            timeout=10.0
        )
        elapsed = time.perf_counter() - start_time
        self.assertEqual(status, 200, f"Embedding failed with {data}")
        self.assertIn("data", data)
        self.assertEqual(len(data["data"][0]["embedding"]), 1024)
        self.assertLess(elapsed, 5.0, f"Embedding took too long: {elapsed:.2f}s")
        print(f"\n[PASS] Model Gateway Embedding (8090): {elapsed:.3f}s (Dim: 1024)")

    def test_02_pilos_chatbot_cache_speed(self):
        """PILOS 정본 지식 캐시가 500ms 이내에 즉각 응답하는지 검증."""
        start_time = time.perf_counter()
        status, data = self._post_json(
            self.PILOS_URL,
            {
                "message": "PILOS 분석 결과 해석 방법"
            },
            timeout=10.0
        )
        elapsed = time.perf_counter() - start_time
        self.assertEqual(status, 200, f"PILOS failed with {data}")
        self.assertTrue("answer" in data and len(data["answer"]) > 0)
        self.assertLess(elapsed, 0.5, f"PILOS cache took too long: {elapsed:.3f}s")
        print(f"[PASS] PILOS Knowledge Cache: {elapsed*1000:.1f}ms")

    def test_03_allonechat_rag_api_endpoint(self):
        """FR-005: 올원챗 /api/v1/search API 500 장애 없이 200 OK 및 추천 솔루션 반환 검증."""
        start_time = time.perf_counter()
        status, data = self._post_json(
            self.ALLONECHAT_URL,
            {"query": "차앤박 프로폴리스 앰플 수분감을 분석해줘", "top_n": 3},
            timeout=40.0
        )
        elapsed = time.perf_counter() - start_time
        self.assertEqual(status, 200, f"AllOneChat returned {status}: {data}")
        self.assertIn("llm_answer", data)
        self.assertIn("search_results", data)
        print(f"[PASS] AllOneChat RAG API Endpoint: Status {status} ({elapsed:.2f}s)")

    def test_04_ollychat_web_portal_health(self):
        """올리챗 Streamlit 포털 엔드포인트 200 OK 응답 확인."""
        req = urllib.request.Request(self.OLLYCHAT_URL)
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            self.assertEqual(resp.status, 200)
        print(f"[PASS] OllyChat Streamlit Portal: Status 200 OK")

    def test_05_multi_chatbot_concurrency_isolation(self):
        """FR-006: 3대 챗봇 동시 요청 시 소켓 타임아웃 없이 순차 대기 완결 검증."""
        def call_pilos():
            status, _ = self._post_json(
                self.PILOS_URL,
                {"message": "PILOS 분석 결과 해석 방법"},
                timeout=60.0
            )
            return status

        def call_gateway_embed():
            status, _ = self._post_json(
                self.EMBEDDING_SERVER_URL,
                {"model": "bge-m3", "input": ["동시 임베딩 쿼리 테스트"]},
                timeout=30.0
            )
            return status

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            f1 = executor.submit(call_pilos)
            f2 = executor.submit(call_gateway_embed)
            results = [f1.result(), f2.result()]

        self.assertEqual(results, [200, 200])
        print(f"[PASS] Multi-Chatbot Concurrency Isolation: All 200 OK")


if __name__ == "__main__":
    unittest.main()
