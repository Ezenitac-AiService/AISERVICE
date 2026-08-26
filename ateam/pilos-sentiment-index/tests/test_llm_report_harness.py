"""
Unit tests for PILOS Execution Harness (Spec 035 T021).
"""

import unittest
from pilos.collection.ai_clients.llm_report_client import PilosExecutionHarness


class TestPilosExecutionHarness(unittest.TestCase):
    def test_pilos_execution_harness_batch_packaging(self):
        docs = [
            {"title": f"반도체 뉴스 {i}", "content": f"상반기 실적 호조 {i}", "date": "2026-08-26", "source": "연합뉴스"}
            for i in range(1, 51)
        ]
        prompt = PilosExecutionHarness.package_batch_prompt(docs, "50개 뉴스를 종합하여 시장 감성 지수를 산출하세요.")
        
        self.assertIn('<market_documents total_count="50">', prompt)
        self.assertIn('<doc id="1"', prompt)
        self.assertIn('<doc id="50"', prompt)
        self.assertIn('</market_documents>', prompt)
        self.assertIn("시장 감성 지수를 산출하세요.", prompt)
        self.assertGreater(len(prompt), 2000)


if __name__ == "__main__":
    unittest.main()
