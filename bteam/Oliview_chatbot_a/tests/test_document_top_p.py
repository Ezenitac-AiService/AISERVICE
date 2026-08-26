"""Unit Tests for Document-Level Top-P & Score Cliff Truncation (Spec 037 US3)."""
import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from oliview_core.utils.document_top_p import DocumentTopPCalculator
from oliview_core.models.citation_models import DocumentTopPConfig


class TestDocumentTopP(unittest.TestCase):

    def test_score_cliff_truncation(self):
        # 1위 0.95, 2위 0.50 (차이 0.45 > 0.25) -> 1위만 선별되어야 함
        calc = DocumentTopPCalculator(DocumentTopPConfig(score_cliff_delta=0.25))
        candidates = [
            {"score": 0.95, "text": "압도적으로 좋은 1위 리뷰", "rating": 5, "option": "A", "review_id": "r1"},
            {"score": 0.50, "text": "점수 절벽 이후 2위 리뷰", "rating": 3, "option": "A", "review_id": "r2"},
            {"score": 0.48, "text": "3위 리뷰", "rating": 3, "option": "A", "review_id": "r3"},
        ]

        citations = calc.filter_documents(candidates, target_name="테스트 제품")
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0].review_id, "r1")

    def test_cumulative_mass_selection(self):
        # 고른 점수 분포 -> 누적 85% 질량까지 가변 선별
        calc = DocumentTopPCalculator(DocumentTopPConfig(cumulative_mass_threshold=0.85))
        candidates = [
            {"score": 0.85, "text": "1위 리뷰", "rating": 5, "option": "A", "review_id": "r1"},
            {"score": 0.84, "text": "2위 리뷰", "rating": 5, "option": "A", "review_id": "r2"},
            {"score": 0.83, "text": "3위 리뷰", "rating": 5, "option": "A", "review_id": "r3"},
            {"score": 0.82, "text": "4위 리뷰", "rating": 5, "option": "A", "review_id": "r4"},
            {"score": 0.81, "text": "5위 리뷰", "rating": 4, "option": "A", "review_id": "r5"},
        ]

        citations = calc.filter_documents(candidates, target_name="테스트 제품")
        self.assertGreaterEqual(len(citations), 2)
        self.assertLessEqual(len(citations), 5)


if __name__ == "__main__":
    unittest.main()
