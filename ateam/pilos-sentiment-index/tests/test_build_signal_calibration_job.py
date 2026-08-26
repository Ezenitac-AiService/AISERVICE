import tempfile
import unittest

from pathlib import Path

import pandas as pd

from pilos.jobs.build_signal_calibration import (
    REQUIRED_CSV_COLUMNS,
    build_signal_calibration,
)
from pilos.jobs.export_ridge_v4_training_reinference import CSV_COLUMNS
from pilos.storage.signal_calibration_store import (
    load_signal_calibration,
)
from tests.test_signal_calibration import (
    NEGATIVE_ARTIFACT_ID,
    POSITIVE_ARTIFACT_ID,
    negative_scores,
    positive_scores,
)


def reinference_rows(**changes):
    """export_ridge_v4_training_reinference CSV의 필수 컬럼만 흉내 낸다."""
    rows = []
    for model_variant, artifact_id, scores in (
        ("positive", POSITIVE_ARTIFACT_ID, positive_scores()),
        ("negative", NEGATIVE_ARTIFACT_ID, negative_scores()),
    ):
        for score in scores:
            row = {
                "artifact_id": artifact_id,
                "artifact_type": "ridge_text_grouped_random_bundle",
                "model_name": "ridge_supply",
                "model_variant": model_variant,
                "model_version": 4,
                "artifact_schema_version": 2,
                "tokenizer_version": "kiwi_ver1",
                "vectorizer_name": "TfidfVectorizer",
                "scaler_name": "not_used",
                "dataset_start_date": "2025-01-02",
                "dataset_end_date": "2026-07-24",
                "predicted_score": score,
                "source_scope": (
                    "training_dataset_reinference_until_2026-07-24"
                ),
            }
            row.update(changes)
            rows.append(row)
    return rows


def write_csv(directory, rows):
    csv_path = Path(directory) / "reinference.csv"
    pd.DataFrame.from_records(rows).to_csv(csv_path, index=False)
    return csv_path


class ReinferenceCsvContractTest(unittest.TestCase):
    """CSV 생산자와 소비자의 컬럼 계약이 어긋나지 않는지 확인한다."""

    def test_required_columns_exist_in_export_contract(self):
        missing = set(REQUIRED_CSV_COLUMNS) - set(CSV_COLUMNS)

        self.assertEqual(missing, set())

    def test_identity_columns_match_artifacts_table(self):
        # artifacts 테이블에 없는 컬럼을 모델 식별에 사용하면 값이 항상
        # 비어 calibration이 어떤 모델의 분포인지 확인할 수 없게 된다.
        artifacts_table_columns = {
            "artifact_id",
            "artifact_type",
            "saved_path",
            "artifact_schema_version",
            "model_name",
            "model_variant",
            "model_version",
            "vectorizer_name",
            "scaler_name",
            "tokenizer_version",
            "dataset_start_date",
            "dataset_end_date",
            "validation_start_date",
            "train_record_count",
            "validation_record_count",
            "train_mae",
            "train_rmse",
            "train_r2",
            "validation_mae",
            "validation_rmse",
            "validation_r2",
        }
        identity_columns = {
            "artifact_id",
            "artifact_type",
            "model_name",
            "model_variant",
            "model_version",
            "artifact_schema_version",
            "tokenizer_version",
            "vectorizer_name",
            "scaler_name",
            "dataset_start_date",
            "dataset_end_date",
        }

        self.assertTrue(identity_columns <= set(REQUIRED_CSV_COLUMNS))
        self.assertTrue(identity_columns <= artifacts_table_columns)


class BuildSignalCalibrationJobTest(unittest.TestCase):
    def test_calibration_is_built_from_actual_reinference_scores(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_path = write_csv(directory, reinference_rows())
            output_path = Path(directory) / "calibration.json"
            summary = build_signal_calibration(
                reinference_csv_path=csv_path,
                output_path=output_path,
            )
            calibration = load_signal_calibration(output_path)

        self.assertEqual(summary["model_name"], "ridge_supply")
        self.assertEqual(summary["model_version"], 4)
        self.assertEqual(summary["source_row_count"], 400)
        self.assertEqual(
            summary["variants"]["positive"]["artifact_id"],
            POSITIVE_ARTIFACT_ID,
        )
        self.assertEqual(calibration.tokenizer_version, "kiwi_ver1")
        self.assertEqual(calibration.vectorizer_name, "TfidfVectorizer")
        self.assertEqual(calibration.scaler_name, "not_used")
        self.assertEqual(
            calibration.artifact_type,
            "ridge_text_grouped_random_bundle",
        )
        self.assertEqual(calibration.dataset_start_date, "2025-01-02")
        self.assertEqual(calibration.dataset_end_date, "2026-07-24")

        positive = calibration.variant("positive")
        self.assertEqual(positive.sample_count, 200)
        self.assertAlmostEqual(positive.quantile_scores[0], 0.0, places=6)
        self.assertAlmostEqual(positive.quantile_scores[-1], 1.99, places=6)

        negative = calibration.variant("negative")
        self.assertAlmostEqual(negative.quantile_scores[0], -1.99, places=6)
        self.assertAlmostEqual(negative.quantile_scores[-1], 0.0, places=6)

    def test_missing_variant_is_rejected(self):
        rows = [
            row
            for row in reinference_rows()
            if row["model_variant"] == "positive"
        ]
        with tempfile.TemporaryDirectory() as directory:
            csv_path = write_csv(directory, rows)
            with self.assertRaisesRegex(ValueError, "positive와 negative"):
                build_signal_calibration(
                    reinference_csv_path=csv_path,
                    output_path=Path(directory) / "calibration.json",
                )

    def test_empty_identity_value_is_rejected(self):
        rows = reinference_rows(vectorizer_name=None)
        with tempfile.TemporaryDirectory() as directory:
            csv_path = write_csv(directory, rows)
            with self.assertRaisesRegex(ValueError, "vectorizer_name"):
                build_signal_calibration(
                    reinference_csv_path=csv_path,
                    output_path=Path(directory) / "calibration.json",
                )

    def test_mixed_model_identity_is_rejected(self):
        rows = reinference_rows()
        rows[0]["tokenizer_version"] = "kiwi_ver2"
        with tempfile.TemporaryDirectory() as directory:
            csv_path = write_csv(directory, rows)
            with self.assertRaisesRegex(ValueError, "모델 식별 값"):
                build_signal_calibration(
                    reinference_csv_path=csv_path,
                    output_path=Path(directory) / "calibration.json",
                )

    def test_multiple_artifact_ids_for_one_variant_is_rejected(self):
        rows = reinference_rows()
        rows[0]["artifact_id"] = 999
        with tempfile.TemporaryDirectory() as directory:
            csv_path = write_csv(directory, rows)
            with self.assertRaisesRegex(ValueError, "여러 artifact_id"):
                build_signal_calibration(
                    reinference_csv_path=csv_path,
                    output_path=Path(directory) / "calibration.json",
                )

    def test_missing_csv_reports_required_export_job(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                FileNotFoundError,
                "export_ridge_v4_training_reinference",
            ):
                build_signal_calibration(
                    reinference_csv_path=Path(directory) / "absent.csv",
                    output_path=Path(directory) / "calibration.json",
                )

    def test_existing_calibration_is_not_overwritten_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_path = write_csv(directory, reinference_rows())
            output_path = Path(directory) / "calibration.json"
            build_signal_calibration(
                reinference_csv_path=csv_path,
                output_path=output_path,
            )
            with self.assertRaises(FileExistsError):
                build_signal_calibration(
                    reinference_csv_path=csv_path,
                    output_path=output_path,
                )


if __name__ == "__main__":
    unittest.main()
