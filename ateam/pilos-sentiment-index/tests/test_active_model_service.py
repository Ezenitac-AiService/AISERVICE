import unittest
from datetime import date
from unittest.mock import patch

from pilos.service import active_model_service


def _record(variant: str, artifact_id: int, saved_path: str) -> dict:
    return {
        "artifact_id": artifact_id,
        "saved_path": saved_path,
        "model_name": "ridge_supply",
        "model_variant": variant,
        "model_version": 4,
        "artifact_schema_version": 2,
        "tokenizer_version": "kiwi_ver1",
        "dataset_start_date": date(2026, 7, 1),
        "dataset_end_date": date(2026, 7, 24),
    }


class ActiveModelCacheTest(unittest.TestCase):
    def setUp(self):
        active_model_service._load_context.cache_clear()
        active_model_service._load_tokenizer.cache_clear()
        self.records = {
            "positive": _record("positive", 7, "artifacts/positive.pkl"),
            "negative": _record("negative", 8, "artifacts/negative.pkl"),
        }

    def tearDown(self):
        active_model_service._load_context.cache_clear()
        active_model_service._load_tokenizer.cache_clear()

    @patch("pilos.service.active_model_service.load_registered_model_artifacts")
    @patch("pilos.service.active_model_service.select_model_artifact")
    def test_bundle_cache_changes_when_full_artifact_identity_changes(
        self,
        select_artifact,
        load_artifacts,
    ):
        select_artifact.side_effect = lambda **kwargs: self.records[
            kwargs["model_variant"]
        ]
        load_artifacts.side_effect = lambda **kwargs: (
            self.records[kwargs["model_variant"]],
            {"model_variant": kwargs["model_variant"]},
        )

        first = active_model_service.get_active_service_model_context()
        second = active_model_service.get_active_service_model_context()

        self.assertIs(first, second)
        self.assertEqual(load_artifacts.call_count, 2)

        self.records["positive"] = _record(
            "positive", 9, "artifacts/positive-next.pkl"
        )
        changed = active_model_service.get_active_service_model_context()

        self.assertEqual(changed.positive_artifact_id, 9)
        self.assertEqual(load_artifacts.call_count, 4)


if __name__ == "__main__":
    unittest.main()
