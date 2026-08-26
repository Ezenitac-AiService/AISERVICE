import os
import sys
import unittest

# Ensure bteam is in python path
BTEAM_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BTEAM_DIR not in sys.path:
    sys.path.insert(0, BTEAM_DIR)
if os.path.join(BTEAM_DIR, "Oliview_chatbot_a") not in sys.path:
    sys.path.insert(0, os.path.join(BTEAM_DIR, "Oliview_chatbot_a"))
if os.path.join(BTEAM_DIR, "Oliview_chatbot_b") not in sys.path:
    sys.path.insert(0, os.path.join(BTEAM_DIR, "Oliview_chatbot_b"))


class TestChatbotStability(unittest.TestCase):
    def setUp(self):
        self.sample_products_dict = [
            {
                "product_name": "차앤박 프로폴리스 앰플",
                "brand_name": "차앤박 (CNP)",
                "category": "스킨케어",
                "separated_sentence": "속건조가 심해서 아무 크림이나 맛바르면 얼굴도 붉고 먼지나도 간지러운데 이건 너무 촉촉하고 속당김이 전혀 없습니다. " * 3,
                "display_name": "수분감",
                "sentiment_label": "긍정",
                "rank": 1
            },
            {
                "product_name": "식물나라 티트리 진정 토너",
                "brand_name": "식물나라",
                "category": "스킨케어",
                "separated_sentence": "트러블 피부에 진정 효과가 정말 뛰어나고 끈적이지 않아서 좋습니다.",
                "display_name": "진정효과",
                "sentiment_label": "긍정",
                "rank": 2
            }
        ]

    def test_chatbot_b_budget_context_documents_with_9b(self):
        """Chatbot B budget_context_documents must safely handle 9B model without NameError."""
        from Oliview_chatbot_b.common import budget_context_documents

        # Call with 9b model
        res = budget_context_documents(self.sample_products_dict, model_name="qwen3.5-9b")
        self.assertIsNotNone(res)
        self.assertEqual(len(res), 2)
        # Verify sentence was trimmed for 9B
        first_sent = res[0]["separated_sentence"] if isinstance(res[0], dict) else res[0].separated_sentence
        self.assertTrue(len(first_sent) <= 150)

    def test_chatbot_b_budget_context_documents_with_kwargs_budget(self):
        """Chatbot B budget_context_documents must safely handle kwargs like budget=1500, is_9b=True."""
        from Oliview_chatbot_b.common import budget_context_documents

        res = budget_context_documents(self.sample_products_dict, budget=1500, is_9b=True)
        self.assertIsNotNone(res)
        self.assertEqual(len(res), 2)

    def test_chatbot_a_budget_context_documents_with_9b(self):
        """Chatbot A budget_context_documents must safely handle 9B model without NameError."""
        from Oliview_chatbot_a.llm_common import budget_context_documents

        res = budget_context_documents(self.sample_products_dict, model_name="qwen3.5-9b")
        self.assertIsNotNone(res)
        self.assertEqual(len(res), 2)

    def test_chatbot_a_budget_context_documents_with_4b(self):
        """Chatbot A budget_context_documents must safely handle 4B model."""
        from Oliview_chatbot_a.llm_common import budget_context_documents

        res = budget_context_documents(self.sample_products_dict, model_name="qwen3.5-4b")
        self.assertIsNotNone(res)
        self.assertEqual(len(res), 2)


if __name__ == "__main__":
    unittest.main()
