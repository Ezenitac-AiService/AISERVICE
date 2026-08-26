"""Unit Tests for Zero-Search Hallucination Guard (Spec 037 US2)."""
import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from oliview_core.nodes.synthesis_node import _extract_doc_ids, ZERO_SEARCH_PROMPT, SINGLE_PROMPT


class TestZeroSearchGuard(unittest.TestCase):

    def test_extract_doc_ids_empty(self):
        state = {
            "reranked_contexts": {},
        }
        doc_ids = _extract_doc_ids(state)
        self.assertEqual(len(doc_ids), 0)

    def test_zero_search_prompt_guidelines(self):
        # 제로 서치 템플릿에 환각 금지 및 정직한 고지 지침이 존재하는지 검증
        self.assertIn("실제 구매자 리뷰를 현재 올리브영 데이터베이스에서 찾을 수 없습니다", ZERO_SEARCH_PROMPT)
        self.assertIn("절대로 임의의 가짜 후기나 창작된 문장", ZERO_SEARCH_PROMPT)


if __name__ == "__main__":
    unittest.main()
