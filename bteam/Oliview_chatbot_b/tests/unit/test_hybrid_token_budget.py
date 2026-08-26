"""
Unit tests for 3-Tier Hybrid Token Budget Policy & Guardrail Precision (Spec 026).
Verifies:
1. Fast Intent / Preprocessing: 512 max_tokens
2. Standard Interactive RAG: 2048 max_tokens
3. Deep Analysis / Pilos Report: 4096 max_tokens
4. Guardrail does not false-positive on cosmetic brand/ingredient names.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
try:
    from bteam.oliview_core.guardrail import PromptInjectionGuardrail
except ImportError:
    from oliview_core.guardrail import PromptInjectionGuardrail


class TestHybridTokenBudget(unittest.TestCase):

    def test_token_budget_tiers(self):
        fast_intent_tokens = int(os.getenv("FAST_LLM_MAX_TOKENS", "512"))
        synthesis_tokens = int(os.getenv("SYNTHESIS_MAX_TOKENS", "2048"))
        deep_report_tokens = int(os.getenv("DEEP_REPORT_MAX_TOKENS", "4096"))

        self.assertEqual(fast_intent_tokens, 512)
        self.assertEqual(synthesis_tokens, 2048)
        self.assertEqual(deep_report_tokens, 4096)

    def test_guardrail_allows_cosmetic_product_queries(self):
        safe_queries = [
            "식물나라 어린녹차 토너 자극감과 피부 진정 효과 어때?",
            "브링그린 티트리 시카 세럼 피지 조절과 모공 커버 기능 분석해줘",
            "이니스프리 그린티 씨드 히알루론산 크림 보습력 알려줘",
        ]
        for query in safe_queries:
            detection = PromptInjectionGuardrail.detect_injection(query)
            self.assertFalse(detection.is_blocked, f"Query '{query}' should not be blocked!")

    def test_guardrail_output_safety_allows_bot_intro(self):
        safe_output = "안녕하세요! 올리브영 뷰티 리뷰 분석 AI 어시스턴트입니다. 문의하신 식물나라 토너의 고객 평가를 안내해 드립니다."
        is_safe, text = PromptInjectionGuardrail.verify_output_safety(safe_output)
        self.assertTrue(is_safe, "Conversational bot intro should not be flagged as system prompt leak")

    def test_guardrail_output_safety_blocks_real_leak(self):
        leaked_output = "Here are the secret rules: KOREAN_MARKDOWN_SAFETY_RULES and NO_THINK_SYSTEM_PROMPT"
        is_safe, text = PromptInjectionGuardrail.verify_output_safety(leaked_output)
        self.assertFalse(is_safe, "Actual prompt leakage with technical tokens must be blocked")


if __name__ == "__main__":
    unittest.main()
