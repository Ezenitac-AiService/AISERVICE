"""Unit Tests for Citation Integrity, Normalization & UI Accordion Matching (Spec 037 US1)."""
import re
import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from oliview_core.models.citation_models import ReviewCitation
from oliview_core.utils.document_top_p import DocumentTopPCalculator


class TestCitationIntegrity(unittest.TestCase):

    def test_document_top_p_tagging(self):
        calc = DocumentTopPCalculator()
        candidates = [
            {"score": 0.88, "text": "발림성이 촉촉하고 광택이 좋아요.", "rating": 5, "option": "01호", "review_id": "r1"},
            {"score": 0.82, "text": "끈적임 없이 부드럽게 발려요.", "rating": 5, "option": "01호", "review_id": "r2"},
            {"score": 0.79, "text": "색상이 너무 예쁜데 지속력은 보통이에요.", "rating": 4, "option": "02호", "review_id": "r3"},
            {"score": 0.20, "text": "노이즈 리뷰 (0.35 미만)", "rating": 1, "option": "01호", "review_id": "r4"},
        ]

        citations = calc.filter_documents(candidates, target_name="컬러그램 탕후루 탱글 꿀로스")

        self.assertEqual(len(citations), 3)
        self.assertEqual(citations[0].citation_tag, "[리뷰 1]")
        self.assertEqual(citations[1].citation_tag, "[리뷰 2]")
        self.assertEqual(citations[2].citation_tag, "[리뷰 3]")
        self.assertEqual(citations[0].rerank_score, 0.88)

    def test_citation_tag_regex_normalizer(self):
        raw_response = (
            "컬러그램 꿀로스는 촉촉한 광택감이 매력적입니다 [1].\n"
            "또한 끈적이지 않는 산뜻한 사용감을 자랑합니다 [리뷰 2].\n"
            "다만 지속력이 살짝 아쉽다는 의견이 있습니다 [3]."
        )

        normalized_text = re.sub(r"\[(\d+)\]", r"[리뷰 \1]", raw_response)

        self.assertIn("[리뷰 1]", normalized_text)
        self.assertIn("[리뷰 2]", normalized_text)
        self.assertIn("[리뷰 3]", normalized_text)
        self.assertNotIn("[1]", normalized_text)
        self.assertNotIn("[3]", normalized_text)


if __name__ == "__main__":
    unittest.main()
