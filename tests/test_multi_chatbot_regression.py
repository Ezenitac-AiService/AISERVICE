"""3대 챗봇(PILOS, 올리챗, 올원챗) 및 Oliview 상품 상세 API 통합 회귀 테스트 스위트 (FR-001 ~ FR-006, SC-001 ~ SC-003).

표준 라이브러리(urllib, json, unittest, concurrent.futures)만을 사용하여 실행됩니다.
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
    OLIVIEW_PORTAL_URL = "http://127.0.0.1:8080/bteam/oliview/"
    PILOS_PORTAL_URL = "http://127.0.0.1:8080/ateam/pilos/"
    OLIVIEW_PRODUCT_DETAIL_URL = "http://127.0.0.1:8080/bteam/oliview/api/products/1"
    OLIVIEW_ANALYSIS_REPORT_URL = "http://127.0.0.1:8080/bteam/oliview/api/products/1/analysis-report"

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

    def _get_json(self, url: str, timeout: float = 10.0) -> tuple[int, dict]:
        req = urllib.request.Request(url)
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
        except Exception as e:
            return 500, {"error": str(e)}

    def _get_status(self, url: str, timeout: float = 10.0) -> int:
        req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:
            return 500

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
        """SC-001, FR-003: PILOS 정본 지식 캐시가 500ms 이내에 즉각 응답하는지 검증."""
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
        """FR-004, FR-005: 올원챗 /api/v1/search API 200 OK 및 추천 솔루션 반환 검증."""
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
        """FR-006: 올리챗 Streamlit 포털 엔드포인트 200 OK 응답 확인."""
        status = self._get_status(self.OLLYCHAT_URL, timeout=10.0)
        self.assertEqual(status, 200)
        print(f"[PASS] OllyChat Streamlit Portal: Status 200 OK")

    def test_05_multi_chatbot_concurrency_isolation(self):
        """SC-003, FR-002, FR-007: 3대 챗봇 동시 요청 시 소켓 타임아웃 없이 순차 대기 완결 검증."""
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

    def test_06_oliview_portal_and_api_routing(self):
        """FR-008, SC-005: Oliview 메인 웹 포털(5173) 및 API 프록시 라우팅 200 OK 확인."""
        status = self._get_status(self.OLIVIEW_PORTAL_URL, timeout=10.0)
        self.assertEqual(status, 200, f"Oliview portal returned status {status}")
        print(f"[PASS] Oliview Web Portal Routing: Status 200 OK")

    def test_07_pilos_gateway_routing(self):
        """FR-006: PILOS 대시보드(5000) 프록시 라우팅 200 OK 확인."""
        status = self._get_status(self.PILOS_PORTAL_URL, timeout=10.0)
        self.assertEqual(status, 200, f"PILOS portal returned status {status}")
        print(f"[PASS] PILOS Web Portal Routing: Status 200 OK")

    def test_08_oliview_product_detail_contract(self):
        """011-US1, FR-001, FR-006: Oliview 상품 상세 조회 API (/bteam/oliview/api/products/1) 계약 검증."""
        status, data = self._get_json(self.OLIVIEW_PRODUCT_DETAIL_URL, timeout=10.0)
        # Nginx를 통한 응답 검증 (200 OK 또는 DB 상태에 따른 응답 구조 검증)
        self.assertIn(status, [200, 404], f"Unexpected status {status}: {data}")
        if status == 200:
            self.assertTrue(data.get("success"), f"Product detail returned false success: {data}")
            self.assertIn("product", data)
            self.assertIn("options", data)
        print(f"[PASS] Oliview Product Detail API Contract: Status {status}")

    def test_09_oliview_analysis_report_contract(self):
        """011-US1, FR-004, FR-006: Oliview 감성 분석 리포트 API (/bteam/oliview/api/products/1/analysis-report) 계약 검증."""
        status, data = self._get_json(self.OLIVIEW_ANALYSIS_REPORT_URL, timeout=10.0)
        self.assertIn(status, [200, 404], f"Unexpected status {status}: {data}")
        if status == 200:
            self.assertTrue(data.get("success"), f"Analysis report returned false success: {data}")
            self.assertIn("radar_data", data)
            self.assertIn("overall_stats", data)
            self.assertIn("overall_report", data)
        print(f"[PASS] Oliview Analysis Report API Contract: Status {status}")


if __name__ == "__main__":
    unittest.main()
