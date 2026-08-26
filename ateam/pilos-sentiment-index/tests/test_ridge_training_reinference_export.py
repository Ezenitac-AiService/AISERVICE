import json
import tempfile
import unittest

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from pilos.jobs.export_ridge_v4_training_reinference import (
    CSV_COLUMNS,
    export_ridge_v4_training_reinference,
)


def training_record(
    daily_document_id,
    stock_code,
    model_date,
    target,
):
    return {
        "daily_document_id": daily_document_id,
        "stock_code": stock_code,
        "model_date": model_date,
        "tfidf_text": f"문서_{daily_document_id}",
        "comment_count": daily_document_id * 10,
        "supply_demand_index": target,
    }


def select_training_records(**kwargs):
    if kwargs["supply_direction"] == "positive":
        return [training_record(1, "000660", date(2026, 7, 23), 1.5)]

    return [training_record(2, "005930", date(2026, 7, 24), -1.5)]


def select_stock_metadata(**kwargs):
    assert kwargs["daily_document_ids"] == [1, 2]
    return {
        1: {
            "daily_document_id": 1,
            "stock_id": 10,
            "stock_code": "000660",
            "stock_name": "SK하이닉스",
        },
        2: {
            "daily_document_id": 2,
            "stock_id": 20,
            "stock_code": "005930",
            "stock_name": "삼성전자",
        },
    }


def load_artifacts(**kwargs):
    model_variant = kwargs["model_variant"]
    artifact_record = {
        "artifact_id": 7 if model_variant == "positive" else 8,
        "artifact_type": "ridge_text_grouped_random_bundle",
        "model_name": "ridge_supply",
        "model_variant": model_variant,
        "model_version": 4,
        "artifact_schema_version": 2,
        "vectorizer_name": "TfidfVectorizer",
        "scaler_name": "not_used",
        "tokenizer_version": "kiwi_ver1",
        "dataset_start_date": date(2025, 1, 2),
        "dataset_end_date": date(2026, 7, 24),
    }
    return artifact_record, {"variant": model_variant}


def run_inference(**kwargs):
    model_variant = kwargs["artifact_record"]["model_variant"]
    direction = 1 if model_variant == "positive" else -1
    results = []

    for document in kwargs["daily_documents"]:
        text_score = direction * document["daily_document_id"] / 10
        intercept = direction * 0.2
        results.append(
            {
                "daily_document_id": document["daily_document_id"],
                "predicted_supply_demand_index": intercept + text_score,
                "intercept": intercept,
                "text_score": text_score,
                "recognized_feature_count": 3,
                "positive_keywords": [
                    {
                        "rank": 1,
                        "word": "매수",
                        "tfidf": 0.5,
                        "coefficient": 0.4,
                        "contribution": 0.2,
                    }
                ],
                "negative_keywords": [
                    {
                        "rank": 1,
                        "word": "매도",
                        "tfidf": 0.5,
                        "coefficient": -0.4,
                        "contribution": -0.2,
                    }
                ],
            }
        )

    return results


class RidgeTrainingReinferenceExportTest(unittest.TestCase):
    def test_exports_long_format_csv_and_separate_variant_summary(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory)
            csv_path = output_directory / "result.csv"
            summary_path = output_directory / "summary.json"
            generated_at = datetime(
                2026,
                8,
                5,
                12,
                0,
                tzinfo=ZoneInfo("Asia/Seoul"),
            )

            summary = export_ridge_v4_training_reinference(
                csv_path=csv_path,
                summary_path=summary_path,
                select_training_records=select_training_records,
                select_stock_metadata=select_stock_metadata,
                load_artifacts=load_artifacts,
                run_inference=run_inference,
                generated_at=generated_at,
            )

            dataframe = pd.read_csv(csv_path, keep_default_na=False)
            saved_summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(tuple(dataframe.columns), CSV_COLUMNS)
        self.assertEqual(len(dataframe), 4)
        self.assertEqual(summary, saved_summary)
        self.assertEqual(summary["document_count"], 2)
        self.assertEqual(summary["row_count"], 4)
        self.assertEqual(summary["stock_count"], 2)
        self.assertEqual(summary["positive"]["count"], 2)
        self.assertEqual(summary["negative"]["count"], 2)
        self.assertEqual(
            set(zip(dataframe["daily_document_id"], dataframe["model_variant"])),
            {(1, "positive"), (1, "negative"), (2, "positive"), (2, "negative")},
        )

        positive_used = dataframe[
            (dataframe["daily_document_id"] == 1)
            & (dataframe["model_variant"] == "positive")
        ].iloc[0]
        negative_not_used = dataframe[
            (dataframe["daily_document_id"] == 1)
            & (dataframe["model_variant"] == "negative")
        ].iloc[0]
        self.assertEqual(positive_used["dataset_split"], "train")
        self.assertTrue(bool(positive_used["was_used_for_training"]))
        self.assertEqual(float(positive_used["actual_target"]), 1.5)
        self.assertEqual(negative_not_used["dataset_split"], "")
        self.assertFalse(bool(negative_not_used["was_used_for_training"]))
        self.assertEqual(negative_not_used["actual_target"], "")
        keywords = json.loads(positive_used["positive_contribution_keywords"])
        self.assertEqual(keywords[0]["word"], "매수")
        self.assertEqual(positive_used["stock_name"], "SK하이닉스")

    def test_rejects_prediction_that_does_not_reconstruct(self):
        def invalid_inference(**kwargs):
            results = run_inference(**kwargs)
            results[0]["predicted_supply_demand_index"] += 1
            return results

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory)
            csv_path = output_directory / "result.csv"
            summary_path = output_directory / "summary.json"

            with self.assertRaisesRegex(ValueError, "contribution 합"):
                export_ridge_v4_training_reinference(
                    csv_path=csv_path,
                    summary_path=summary_path,
                    select_training_records=select_training_records,
                    select_stock_metadata=select_stock_metadata,
                    load_artifacts=load_artifacts,
                    run_inference=invalid_inference,
                )

            self.assertFalse(csv_path.exists())
            self.assertFalse(summary_path.exists())

    def test_rejects_duplicate_training_document_in_same_variant(self):
        def duplicate_records(**kwargs):
            records = select_training_records(**kwargs)

            if kwargs["supply_direction"] == "positive":
                return [*records, dict(records[0])]

            return records

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory)

            with self.assertRaisesRegex(ValueError, "중복"):
                export_ridge_v4_training_reinference(
                    csv_path=output_directory / "result.csv",
                    summary_path=output_directory / "summary.json",
                    select_training_records=duplicate_records,
                    select_stock_metadata=select_stock_metadata,
                    load_artifacts=load_artifacts,
                    run_inference=run_inference,
                )


if __name__ == "__main__":
    unittest.main()
