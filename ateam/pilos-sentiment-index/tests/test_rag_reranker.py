import unittest

from pilos.analysis.rag.rag_reranker import rerank_chunks


class RagRerankerTest(unittest.TestCase):
    def test_cosine_similarity_reorders_rrf_candidates(self):
        chunks = [
            {
                "chunk_id": "less-related",
                "text": "덜 관련된 문서",
                "metadata": {"status": "completed"},
                "rrf_score": 0.9,
            },
            {
                "chunk_id": "more-related",
                "text": "더 관련된 문서",
                "metadata": {"status": "completed"},
                "rrf_score": 0.8,
            },
        ]

        results = rerank_chunks(
            chunks,
            query_vector=[1.0, 0.0, 0.0],
            document_vectors=[
                [0.0, 1.0, 0.0],
                [0.9, 0.1, 0.0],
            ],
            top_k=2,
        )

        self.assertEqual(results[0]["chunk_id"], "more-related")
        self.assertEqual(results[0]["rerank_rank"], 1)
        self.assertGreater(
            results[0]["rerank_score"],
            results[1]["rerank_score"],
        )


if __name__ == "__main__":
    unittest.main()
