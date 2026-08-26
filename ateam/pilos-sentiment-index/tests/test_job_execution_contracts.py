import unittest
import json
from datetime import date
from unittest.mock import ANY, patch

import pandas as pd

from pilos.jobs.build_daily_documents import run_daily_document_building
from pilos.jobs.predict_model import main as run_inference_job
from pilos.jobs.predict_model import run_database_inference
from pilos.jobs.tokenize_comments import run_pending_comment_tokenization
from pilos.jobs.train_model import (
    MODEL_TRAINING_CONFIGS,
    TRAINING_TARGET_MODEL_VERSION,
)
from pilos.model_config import ACTIVE_SERVICE_MODEL_VERSION


class ModelVersionBoundaryTest(unittest.TestCase):
    def test_training_target_is_separate_from_active_service_version(self):
        self.assertEqual(ACTIVE_SERVICE_MODEL_VERSION, 4)
        self.assertEqual(TRAINING_TARGET_MODEL_VERSION, 5)
        self.assertNotEqual(
            TRAINING_TARGET_MODEL_VERSION,
            ACTIVE_SERVICE_MODEL_VERSION,
        )
        self.assertEqual(
            {config["model_version"] for config in MODEL_TRAINING_CONFIGS},
            {TRAINING_TARGET_MODEL_VERSION},
        )
        self.assertTrue(
            all(
                f"_v{TRAINING_TARGET_MODEL_VERSION}.pkl"
                in config["model_output_path"].name
                for config in MODEL_TRAINING_CONFIGS
            )
        )


class TokenizationJobContractTest(unittest.TestCase):
    @patch("pilos.jobs.tokenize_comments.select_untokenized_comment_batch")
    @patch("pilos.jobs.tokenize_comments.create_kiwi")
    def test_no_pending_comments_returns_zero(self, create_kiwi, select_batch):
        select_batch.return_value = []

        result = run_pending_comment_tokenization()

        self.assertEqual(result, 0)
        create_kiwi.assert_called_once()

    @patch("pilos.jobs.tokenize_comments.insert_tokenized_comments")
    @patch("pilos.jobs.tokenize_comments.run_comment_tokenization")
    @patch("pilos.jobs.tokenize_comments.select_untokenized_comment_batch")
    @patch("pilos.jobs.tokenize_comments.create_kiwi")
    def test_multiple_batches_return_total_inserted_count(
        self,
        create_kiwi,
        select_batch,
        run_tokenization,
        insert_tokenized,
    ):
        select_batch.side_effect = [
            [{"preprocessed_comment_id": 1, "text": "첫 댓글"}],
            [{"preprocessed_comment_id": 3, "text": "둘째 댓글"}],
            [],
        ]
        run_tokenization.side_effect = [
            pd.DataFrame({"preprocessed_comment_id": [1]}),
            pd.DataFrame({"preprocessed_comment_id": [3]}),
        ]
        insert_tokenized.side_effect = [1, 1]

        result = run_pending_comment_tokenization()

        self.assertEqual(result, 2)
        self.assertEqual(select_batch.call_count, 3)
        self.assertEqual(run_tokenization.call_count, 2)
        self.assertEqual(insert_tokenized.call_count, 2)

    def test_processing_errors_propagate_to_caller(self):
        stages = ("select", "tokenize", "insert")

        for failing_stage in stages:
            with self.subTest(stage=failing_stage):
                with (
                    patch(
                        "pilos.jobs.tokenize_comments.create_kiwi",
                        return_value=object(),
                    ),
                    patch("pilos.jobs.tokenize_comments.logger"),
                    patch(
                        "pilos.jobs.tokenize_comments."
                        "select_untokenized_comment_batch",
                    ) as select_batch,
                    patch(
                        "pilos.jobs.tokenize_comments."
                        "run_comment_tokenization",
                    ) as run_tokenization,
                    patch(
                        "pilos.jobs.tokenize_comments."
                        "insert_tokenized_comments",
                    ) as insert_tokenized,
                ):
                    select_batch.return_value = [
                        {
                            "preprocessed_comment_id": 1,
                            "text": "댓글",
                        }
                    ]
                    run_tokenization.return_value = pd.DataFrame(
                        {"preprocessed_comment_id": [1]}
                    )
                    insert_tokenized.return_value = 1

                    failing_mock = {
                        "select": select_batch,
                        "tokenize": run_tokenization,
                        "insert": insert_tokenized,
                    }[failing_stage]
                    failing_mock.side_effect = RuntimeError(
                        f"{failing_stage} failure"
                    )

                    with self.assertRaisesRegex(
                        RuntimeError,
                        f"{failing_stage} failure",
                    ):
                        run_pending_comment_tokenization()


class DailyDocumentJobContractTest(unittest.TestCase):
    @patch("pilos.jobs.build_daily_documents.logger")
    @patch("pilos.jobs.build_daily_documents.insert_daily_document_with_comments")
    @patch("pilos.jobs.build_daily_documents.create_daily_document_data")
    @patch("pilos.jobs.build_daily_documents.select_tokenized_comments_for_day")
    @patch("pilos.jobs.build_daily_documents.select_pending_daily_document_targets")
    def test_returns_success_and_failure_counts_and_skips_empty_target(
        self,
        select_targets,
        select_comments,
        create_document,
        insert_document,
        logger,
    ):
        select_targets.return_value = [
            {"stock_id": 1, "model_date": date(2026, 7, 25)},
            {"stock_id": 2, "model_date": date(2026, 7, 25)},
            {"stock_id": 3, "model_date": date(2026, 7, 25)},
        ]
        select_comments.side_effect = [
            [{"tokenized_comment_id": 11, "kiwi_tokens": []}],
            RuntimeError("daily document failure"),
            [],
        ]
        create_document.return_value = (
            {"comment_count": 1},
            [{"tokenized_comment_id": 11, "sequence_number": 1}],
        )
        insert_document.return_value = 101

        result = run_daily_document_building()

        self.assertEqual(result, (1, 1))
        self.assertEqual(select_comments.call_count, 3)
        create_document.assert_called_once()
        insert_document.assert_called_once()


class InferenceJobContractTest(unittest.TestCase):
    def setUp(self):
        self.daily_documents = [{"daily_document_id": 1}]
        self.positive_result = {
            "daily_document_id": 1,
            "artifact_id": 7,
        }
        self.negative_result = {
            "daily_document_id": 1,
            "artifact_id": 8,
        }

    @patch("pilos.jobs.predict_model.insert_sentiment_index_results")
    @patch("pilos.jobs.predict_model.run_text_only_inference")
    @patch("pilos.jobs.predict_model.load_registered_model_artifacts")
    @patch("pilos.jobs.predict_model.select_daily_documents_for_inference")
    def test_both_directions_are_saved_in_one_call(
        self,
        select_documents,
        load_artifacts,
        run_inference,
        insert_results,
    ):
        select_documents.return_value = self.daily_documents
        load_artifacts.side_effect = [
            ({"artifact_id": 7}, {"bundle": "positive"}),
            ({"artifact_id": 8}, {"bundle": "negative"}),
        ]
        run_inference.side_effect = [
            [self.positive_result],
            [self.negative_result],
        ]
        insert_results.return_value = {
            "input_count": 2,
            "inserted_count": 2,
            "existing_count": 0,
        }

        results, summary = run_database_inference(
            inference_start_date=date(2026, 7, 25),
            inference_end_date=date(2026, 7, 31),
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(summary["inserted_count"], 2)
        self.assertTrue(
            all(
                call.kwargs["model_version"]
                == ACTIVE_SERVICE_MODEL_VERSION
                for call in load_artifacts.call_args_list
            )
        )
        insert_results.assert_called_once_with(
            inference_results=[
                self.positive_result,
                self.negative_result,
            ]
        )
        select_documents.assert_called_once_with(
            tokenizer_version=ANY,
            inference_start_date=date(2026, 7, 25),
            inference_end_date=date(2026, 7, 31),
            artifact_ids=(7, 8),
        )

    @patch("pilos.jobs.predict_model.insert_sentiment_index_results")
    @patch("pilos.jobs.predict_model.run_text_only_inference")
    @patch("pilos.jobs.predict_model.load_registered_model_artifacts")
    @patch("pilos.jobs.predict_model.select_daily_documents_for_inference")
    def test_no_pending_targets_skips_inference_and_storage(
        self,
        select_documents,
        load_artifacts,
        run_inference,
        insert_results,
    ):
        select_documents.return_value = []
        load_artifacts.side_effect = [
            ({"artifact_id": 7}, {"bundle": "positive"}),
            ({"artifact_id": 8}, {"bundle": "negative"}),
        ]

        results, summary = run_database_inference(
            inference_start_date=date(2026, 7, 25),
            inference_end_date=date(2026, 7, 31),
        )

        self.assertEqual(results, {"positive": [], "negative": []})
        self.assertEqual(summary["input_count"], 0)
        run_inference.assert_not_called()
        insert_results.assert_not_called()

    @patch("builtins.print")
    @patch("pilos.jobs.predict_model.get_current_kst_date")
    @patch("pilos.jobs.predict_model.run_database_inference")
    def test_main_reports_zero_targets_without_index_error(
        self,
        run_inference,
        current_date,
        print_output,
    ):
        current_date.return_value = date(2026, 8, 10)
        run_inference.return_value = (
            {"positive": [], "negative": []},
            {"input_count": 0, "inserted_count": 0, "existing_count": 0},
        )

        run_inference_job()

        summary = json.loads(print_output.call_args.args[0])
        self.assertEqual(summary["storage"]["input_count"], 0)
        self.assertEqual(summary["models"]["positive"]["result_count"], 0)
        self.assertIsNone(summary["models"]["positive"]["artifact_id"])

    @patch("pilos.jobs.predict_model.insert_sentiment_index_results")
    @patch("pilos.jobs.predict_model.run_text_only_inference")
    @patch("pilos.jobs.predict_model.load_registered_model_artifacts")
    @patch("pilos.jobs.predict_model.select_daily_documents_for_inference")
    def test_direction_failure_prevents_storage(
        self,
        select_documents,
        load_artifacts,
        run_inference,
        insert_results,
    ):
        select_documents.return_value = self.daily_documents
        load_artifacts.side_effect = [
            ({"artifact_id": 7}, {"bundle": "positive"}),
            ({"artifact_id": 8}, {"bundle": "negative"}),
        ]
        run_inference.side_effect = [
            [self.positive_result],
            RuntimeError("negative inference failure"),
        ]

        with self.assertRaisesRegex(
            RuntimeError,
            "negative inference failure",
        ):
            run_database_inference(
                inference_start_date=date(2026, 7, 25),
                inference_end_date=date(2026, 7, 31),
            )

        insert_results.assert_not_called()

    @patch("pilos.jobs.predict_model.insert_sentiment_index_results")
    @patch("pilos.jobs.predict_model.run_text_only_inference")
    @patch("pilos.jobs.predict_model.load_registered_model_artifacts")
    @patch("pilos.jobs.predict_model.select_daily_documents_for_inference")
    def test_storage_failure_propagates(
        self,
        select_documents,
        load_artifacts,
        run_inference,
        insert_results,
    ):
        select_documents.return_value = self.daily_documents
        load_artifacts.side_effect = [
            ({"artifact_id": 7}, {"bundle": "positive"}),
            ({"artifact_id": 8}, {"bundle": "negative"}),
        ]
        run_inference.side_effect = [
            [self.positive_result],
            [self.negative_result],
        ]
        insert_results.side_effect = RuntimeError("storage failure")

        with self.assertRaisesRegex(
            RuntimeError,
            "storage failure",
        ):
            run_database_inference(
                inference_start_date=date(2026, 7, 25),
                inference_end_date=date(2026, 7, 31),
            )

    @patch("pilos.jobs.predict_model.select_daily_documents_for_inference")
    def test_prevents_historical_backfill_before_automatic_start_date(
        self,
        select_documents,
    ):
        with self.assertRaisesRegex(
            ValueError,
            "자동 추론 시작일",
        ):
            run_database_inference(
                inference_start_date=date(2026, 7, 24),
                inference_end_date=date(2026, 7, 31),
            )

        select_documents.assert_not_called()


if __name__ == "__main__":
    unittest.main()
