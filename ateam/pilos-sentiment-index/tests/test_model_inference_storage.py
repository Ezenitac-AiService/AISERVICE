import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from pilos.storage.model_inference_db import (
    insert_sentiment_index_results,
    select_daily_documents_for_inference,
)


class InferenceStorageTest(unittest.TestCase):
    def inference_result(self):
        return {
            "daily_document_id": 1,
            "artifact_id": 7,
            "predicted_supply_demand_index": 0.1,
            "intercept": 0.0,
            "text_score": 0.1,
            "recognized_feature_count": 2,
            "unique_token_count": 3,
            "vocabulary_coverage": 2 / 3,
            "inference_status": "insufficient_features",
            "positive_keywords": [],
            "negative_keywords": [],
        }

    @patch("pilos.storage.model_inference_db.get_engine")
    def test_inserts_quality_fields_for_new_result(self, get_engine):
        conn = MagicMock()
        conn.execute.side_effect = [MagicMock(mappings=lambda: []), None]
        engine = MagicMock()
        engine.begin.return_value.__enter__.return_value = conn
        get_engine.return_value = engine

        summary = insert_sentiment_index_results(
            inference_results=[self.inference_result()]
        )

        insert_statement, insert_values = conn.execute.call_args_list[1].args
        self.assertIn("unique_token_count", str(insert_statement))
        self.assertIn("vocabulary_coverage", str(insert_statement))
        self.assertIn("inference_status", str(insert_statement))
        self.assertEqual(insert_values[0]["unique_token_count"], 3)
        self.assertEqual(insert_values[0]["inference_status"], "insufficient_features")
        self.assertEqual(summary["inserted_count"], 1)

    @patch("pilos.storage.model_inference_db.get_engine")
    def test_existing_result_is_not_updated(self, get_engine):
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value = [
            {"daily_document_id": 1, "artifact_id": 7}
        ]
        engine = MagicMock()
        engine.begin.return_value.__enter__.return_value = conn
        get_engine.return_value = engine

        summary = insert_sentiment_index_results(
            inference_results=[self.inference_result()]
        )

        self.assertEqual(conn.execute.call_count, 1)
        self.assertEqual(summary["inserted_count"], 0)
        self.assertEqual(summary["existing_count"], 1)

    @patch("pilos.storage.model_inference_db.get_engine")
    def test_select_only_includes_missing_artifact_results(self, get_engine):
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value = []
        engine = MagicMock()
        engine.connect.return_value.__enter__.return_value = conn
        get_engine.return_value = engine

        result = select_daily_documents_for_inference(
            tokenizer_version="kiwi_ver1",
            inference_start_date=date(2026, 7, 25),
            inference_end_date=date(2026, 8, 10),
            artifact_ids=(7, 8),
        )

        statement = str(conn.execute.call_args.args[0])
        self.assertEqual(result, [])
        self.assertIn("COUNT(DISTINCT sir.artifact_id)", statement)
        self.assertNotIn("UPDATE sentiment_index_result", statement)


if __name__ == "__main__":
    unittest.main()
