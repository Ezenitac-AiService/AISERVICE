import unittest
from datetime import datetime
from unittest.mock import Mock

import numpy as np

from pilos.analysis.daily_dataset import iter_daily_documents
from pilos.analysis.review import _iter_records_with_token_samples
from pilos.analysis.modeling.ridge_model import create_ridge_model
from pilos.analysis.vectorizer import (
    create_tfidf_vectorizer,
    tokens_to_tfidf_text,
)
from pilos.jobs.predict_model import run_text_only_inference


class VectorizerContractTest(unittest.TestCase):
    def test_tokens_to_tfidf_text_uses_form_and_preserves_internal_spaces(self):
        tokens = [
            {"form": "젠슨 황", "tag": "NNP"},
            {"form": "반도체", "tag": "NNG"},
        ]

        result = tokens_to_tfidf_text(tokens)

        self.assertEqual(result, "젠슨_황 반도체")

    def test_inference_uses_fitted_vectorizer_transform(self):
        vectorizer = create_tfidf_vectorizer(
            min_df=1,
            max_df=1.0,
        )
        training_features = vectorizer.fit_transform(
            ["상승 기대", "하락 우려"]
        )
        ridge_model = create_ridge_model()
        ridge_model.fit(
            training_features,
            np.array([0.5, -0.5]),
        )
        transform = Mock(wraps=vectorizer.transform)
        vectorizer.transform = transform

        results = run_text_only_inference(
            daily_documents=[
                {
                    "daily_document_id": 1,
                    "stock_code": "005930",
                    "model_date": datetime(2026, 7, 25).date(),
                    "tfidf_text": "상승 기대",
                    "comment_count": 2,
                }
            ],
            artifact_record={
                "artifact_id": 7,
                "model_name": "ridge_supply",
                "model_variant": "positive",
                "model_version": 4,
            },
            model_artifacts={
                "vectorizer": vectorizer,
                "ridge_model": ridge_model,
            },
        )

        transform.assert_called_once()
        self.assertEqual(len(results), 1)
        self.assertTrue(
            np.isfinite(
                results[0]["predicted_supply_demand_index"]
            )
        )


class DailyDocumentBoundaryTest(unittest.TestCase):
    def test_daily_document_accepts_datetime_and_keeps_existing_rules(self):
        records = [
            {
                "stock_code": "005930",
                "created_at": datetime(2026, 7, 25, 9, 0),
                "kiwi_tokens": [{"form": "상승", "tag": "NNG"}],
            },
            {
                "stock_code": "005930",
                "created_at": datetime(2026, 7, 25, 10, 0),
                "kiwi_tokens": [],
            },
            {
                "stock_code": "005930",
                "created_at": datetime(2026, 7, 25, 15, 30),
                "kiwi_tokens": [{"form": "제외", "tag": "NNG"}],
            },
        ]

        documents = list(iter_daily_documents(records))

        self.assertEqual(
            documents,
            [
                {
                    "stock_code": "005930",
                    "model_date": datetime(2026, 7, 25).date(),
                    "tfidf_text": "상승",
                    "comment_count": 2,
                }
            ],
        )

    def test_daily_document_rejects_unnormalized_created_at(self):
        records = [
            {
                "stock_code": "005930",
                "created_at": "2026-07-25T09:00:00",
                "kiwi_tokens": [],
            }
        ]

        with self.assertRaisesRegex(
            ValueError,
            "정규화된 datetime",
        ):
            list(iter_daily_documents(records))

    def test_review_boundary_normalizes_created_at_without_mutating_input(self):
        record = {
            "stock_code": "005930",
            "created_at": "2026-07-25T09:00:00+09:00",
            "kiwi_tokens": [],
        }

        normalized = list(
            _iter_records_with_token_samples(
                records=[record],
                token_sample_rows=[],
                sample_counts={},
                sample_size=0,
            )
        )

        self.assertIsInstance(
            normalized[0]["created_at"],
            datetime,
        )
        self.assertEqual(
            record["created_at"],
            "2026-07-25T09:00:00+09:00",
        )


if __name__ == "__main__":
    unittest.main()
