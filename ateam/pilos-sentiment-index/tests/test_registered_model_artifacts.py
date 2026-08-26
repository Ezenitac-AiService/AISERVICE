import unittest

from datetime import date
from pathlib import Path
from unittest.mock import patch

from pilos.storage.model_artifacts import (
    load_registered_model_artifacts,
    resolve_registered_model_path,
)


class RegisteredModelArtifactsTest(unittest.TestCase):
    def test_repository_relative_model_path_is_resolved(self):
        base_dir = Path.cwd()

        result = resolve_registered_model_path(
            saved_path="artifacts/model.pkl",
            base_dir=base_dir,
        )

        self.assertEqual(
            result,
            (base_dir / "artifacts" / "model.pkl").resolve(),
        )

    def test_path_outside_repository_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "저장소 밖"):
            resolve_registered_model_path(
                saved_path="../model.pkl",
                base_dir=Path.cwd(),
            )

    @patch("pilos.storage.model_artifacts.load_model_artifacts")
    @patch("pilos.storage.model_artifacts.select_model_artifact")
    def test_registered_row_and_bundle_identity_are_checked(
        self,
        select_artifact,
        load_artifacts,
    ):
        identity = {
            "artifact_schema_version": 2,
            "model_name": "ridge_supply",
            "model_variant": "positive",
            "model_version": 4,
            "tokenizer_version": "kiwi_ver1",
            "dataset_start_date": date(2025, 1, 2),
            "dataset_end_date": date(2026, 7, 24),
        }
        select_artifact.return_value = {
            **identity,
            "artifact_id": 7,
            "saved_path": "artifacts/model.pkl",
            "scaler_name": "not_used",
        }
        load_artifacts.return_value = {
            **identity,
            "feature_mode": "text_only",
        }

        record, bundle = load_registered_model_artifacts(
            model_name="ridge_supply",
            model_variant="positive",
            model_version=4,
            artifact_schema_version=2,
            base_dir=Path.cwd(),
        )

        self.assertEqual(record["artifact_id"], 7)
        self.assertEqual(bundle["model_variant"], "positive")


if __name__ == "__main__":
    unittest.main()
