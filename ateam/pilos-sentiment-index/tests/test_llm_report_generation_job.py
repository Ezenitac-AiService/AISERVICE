import logging
import tempfile
import unittest

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from pilos.collection.ai_clients.llm_report_client import LlmReportResponseError
from pilos.dto.llm_report_dto import (
    EVIDENCE_SCHEMA_VERSION,
    PROMPT_VERSION,
    REPORT_SCHEMA_VERSION,
    LlmMarketCommentary,
    ReportGenerationResult,
)
from pilos.jobs.generate_llm_reports import (
    ARTIFACT_SCHEMA_VERSION,
    configure_logging,
    MODEL_NAME,
    MODEL_VERSION,
    _group_latest_document_targets,
    run_pending_llm_report_generation,
)
from pilos.model_config import ACTIVE_SERVICE_MODEL_VERSION
from pilos.storage.llm_report_db import (
    select_latest_llm_report_targets,
    select_signal_history_results,
    update_v13_llm_report_for_supply_change,
)
from tests.test_llm_report_analysis import valid_commentary
from tests.test_signal_calibration import (
    NEGATIVE_ARTIFACT_ID,
    POSITIVE_ARTIFACT_ID,
    make_calibration,
)


def target_row(
    *,
    daily_document_id=10,
    model_variant="positive",
    result_id=100,
    recognized_feature_count=8,
    actual_supply_index=0.08,
    model_date=date(2026, 8, 4),
    positive_score=0.5,
    negative_score=-0.5,
    inference_status="ready",
    supply_data_status="confirmed",
    supply_observed_at=datetime(2026, 8, 4, 15, 30),
):
    return {
        "daily_document_id": daily_document_id,
        "stock_id": 1,
        "stock_code": "005930",
        "stock_name": "삼성전자",
        "model_date": model_date,
        "comment_count": 30,
        "actual_supply_index": actual_supply_index,
        "sentiment_index_result_id": result_id,
        "artifact_id": (
            POSITIVE_ARTIFACT_ID
            if model_variant == "positive"
            else NEGATIVE_ARTIFACT_ID
        ),
        "model_variant": model_variant,
        "supply_demand_association_score": (
            positive_score if model_variant == "positive" else negative_score
        ),
        "intercept": 0.01 if model_variant == "positive" else -0.02,
        "text_score": 0.19 if model_variant == "positive" else -0.08,
        "recognized_feature_count": recognized_feature_count,
        "unique_token_count": 10,
        "vocabulary_coverage": 0.8,
        "inference_status": inference_status,
        "supply_data_status": supply_data_status,
        "supply_observed_at": supply_observed_at,
    }


def positive_row(**changes):
    values = {"model_variant": "positive", "result_id": 100}
    values.update(changes)
    return target_row(**values)


def negative_row(**changes):
    values = {"model_variant": "negative", "result_id": 101}
    values.update(changes)
    return target_row(**values)


def history_rows():
    """직전 두 거래일의 저장된 추론 결과를 흉내 낸다."""
    rows = []
    for offset, (document_id, score) in enumerate(
        ((8, 0.2), (9, 0.3)),
        start=2,
    ):
        model_date = date(2026, 8, 4 - (4 - offset))
        rows.append(
            positive_row(
                daily_document_id=document_id,
                result_id=200 + document_id,
                model_date=model_date,
                positive_score=score,
            )
        )
        rows.append(
            negative_row(
                daily_document_id=document_id,
                result_id=300 + document_id,
                model_date=model_date,
                positive_score=score,
            )
        )
    return rows


def load_test_artifacts(**kwargs):
    return (
        {
            "artifact_id": (
                POSITIVE_ARTIFACT_ID
                if kwargs["model_variant"] == "positive"
                else NEGATIVE_ARTIFACT_ID
            ),
            "artifact_type": "ridge_text_grouped_random_bundle",
            "model_name": "ridge_supply",
            "model_variant": kwargs["model_variant"],
            "model_version": 4,
            "artifact_schema_version": 2,
            "tokenizer_version": "kiwi_ver1",
            "vectorizer_name": "TfidfVectorizer",
            "scaler_name": "not_used",
            "dataset_start_date": date(2025, 1, 2),
            "dataset_end_date": date(2026, 7, 24),
        },
        {},
    )


def run_with(
    rows,
    *,
    history=None,
    existing=None,
    client=None,
    insert_report=None,
    update_report=None,
):
    if client is None:
        client = Mock()
        client.generate_report.return_value = ReportGenerationResult(
            commentary=valid_commentary(
                market_commentary=(
                    "개인투자자 수급은 매수 우위로 관측됐습니다. "
                    "댓글 수급 신호는 과거 동일 방향 대비 높은 수준입니다."
                ),
                conclusion=(
                    "매수 우위 구간에서 오늘의 댓글 신호가 최근보다 높게 "
                    "나타났습니다."
                ),
            ),
            provider_response_id="response-1",
            input_tokens=10,
            output_tokens=20,
        )
    if insert_report is None:
        insert_report = Mock(return_value=1)
    if update_report is None:
        update_report = Mock(return_value=True)

    select_targets = Mock(return_value=rows)
    select_history = Mock(
        return_value=history_rows() if history is None else history
    )
    select_existing = Mock(return_value=[] if existing is None else existing)
    summary = run_pending_llm_report_generation(
        report_start_date=date(2026, 8, 4),
        report_end_date=date(2026, 8, 4),
        client=client,
        provider="academy",
        model="qwen3.5-4b",
        calibration=make_calibration(),
        select_targets=select_targets,
        select_history=select_history,
        select_existing_hashes=select_existing,
        insert_report=insert_report,
        update_report=update_report,
        load_artifacts=Mock(side_effect=load_test_artifacts),
    )
    return summary, client, insert_report, select_targets


def run_with_lazy_client(rows, *, history):
    generated_client = Mock()
    generated_client.generate_report.return_value = ReportGenerationResult(
        commentary=valid_commentary(),
        provider_response_id="response-lazy",
        input_tokens=10,
        output_tokens=20,
    )
    settings = Mock(provider="academy", model="qwen3.5-4b")
    insert_report = Mock(return_value=1)

    with (
        patch(
            "pilos.jobs.generate_llm_reports."
            "LlmReportClientSettings.from_env",
            return_value=settings,
        ) as from_env,
        patch(
            "pilos.jobs.generate_llm_reports."
            "OpenAICompatibleLlmReportClient",
            return_value=generated_client,
        ) as client_constructor,
    ):
        summary = run_pending_llm_report_generation(
            report_start_date=date(2026, 8, 4),
            report_end_date=date(2026, 8, 4),
            provider="academy",
            model="qwen3.5-4b",
            calibration=make_calibration(),
            select_targets=Mock(return_value=rows),
            select_history=Mock(return_value=history),
            select_existing_hashes=Mock(return_value=[]),
            insert_report=insert_report,
            update_report=Mock(return_value=True),
            load_artifacts=Mock(side_effect=load_test_artifacts),
        )

    return (
        summary,
        generated_client,
        insert_report,
        from_env,
        client_constructor,
    )


class ReadOnlyQueryTest(unittest.TestCase):
    def test_target_query_is_read_only_and_drops_keyword_columns(self):
        engine = MagicMock()
        connection = engine.connect.return_value.__enter__.return_value
        connection.execute.return_value.mappings.return_value = []

        with patch(
            "pilos.storage.llm_report_db.get_engine",
            return_value=engine,
        ):
            rows = select_latest_llm_report_targets(
                report_start_date=date(2026, 8, 4),
                report_end_date=date(2026, 8, 4),
                model_name=MODEL_NAME,
                model_version=MODEL_VERSION,
                artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
            )

        statement = str(connection.execute.call_args.args[0]).upper()
        self.assertEqual(rows, [])
        self.assertIn("INNER JOIN SUPPLY_DEMAND", statement)
        self.assertIn("SUPPLY_DEMAND_INDEX AS ACTUAL_SUPPLY_INDEX", statement)
        self.assertNotIn("POSITIVE_CONTRIBUTION_KEYWORDS", statement)
        self.assertNotIn("NEGATIVE_CONTRIBUTION_KEYWORDS", statement)
        self.assertNotIn("PREPROCESSED_COMMENT", statement)
        self.assertNotIn("INSERT ", statement)
        self.assertNotIn("UPDATE ", statement)
        self.assertNotIn("DELETE ", statement)

    def test_history_query_reuses_existing_result_table(self):
        engine = MagicMock()
        connection = engine.connect.return_value.__enter__.return_value
        connection.execute.return_value.mappings.return_value = []

        with patch(
            "pilos.storage.llm_report_db.get_engine",
            return_value=engine,
        ):
            rows = select_signal_history_results(
                stock_ids=[1],
                history_start_date=date(2026, 7, 14),
                history_end_date=date(2026, 8, 4),
                model_name=MODEL_NAME,
                model_version=MODEL_VERSION,
                artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
            )

        statement = str(connection.execute.call_args.args[0]).upper()
        self.assertEqual(rows, [])
        self.assertIn("JOIN SENTIMENT_INDEX_RESULT", " ".join(statement.split()))
        self.assertNotIn("INSERT ", statement)
        self.assertNotIn("CREATE ", statement)

    def test_confirmed_update_is_limited_to_estimated_v13_report(self):
        engine = MagicMock()
        connection = engine.begin.return_value.__enter__.return_value
        connection.execute.return_value.rowcount = 1
        report_record = {
            "status": "ready",
            "report_json": {"commentary_source": "llm"},
            "input_hash": "1" * 64,
            "provider_response_id": "response-1",
            "input_tokens": 10,
            "output_tokens": 20,
            "supply_data_status": "confirmed",
            "supply_observed_at": datetime(2026, 8, 4, 15, 30),
        }

        with patch(
            "pilos.storage.llm_report_db.get_engine",
            return_value=engine,
        ):
            updated = update_v13_llm_report_for_supply_change(
                llm_report_id=13,
                report_record=report_record,
            )

        statement = str(connection.execute.call_args.args[0]).upper()
        self.assertTrue(updated)
        self.assertIn("PROMPT_VERSION = 'MARKET_COMMENTARY_V13'", statement)
        self.assertIn("SUPPLY_DATA_STATUS = 'ESTIMATED'", statement)
        self.assertIn(":SUPPLY_DATA_STATUS = 'CONFIRMED'", statement)
        self.assertIn(":SUPPLY_OBSERVED_AT > SUPPLY_OBSERVED_AT", statement)


class LlmReportGenerationJobTest(unittest.TestCase):
    def test_job_uses_active_service_model_version(self):
        self.assertEqual(MODEL_VERSION, ACTIVE_SERVICE_MODEL_VERSION)

    def test_zero_targets_does_not_create_llm_client(self):
        select_history = Mock(return_value=[])
        with patch(
            "pilos.jobs.generate_llm_reports.LlmReportClientSettings.from_env"
        ) as from_env:
            summary = run_pending_llm_report_generation(
                report_start_date=date(2026, 8, 4),
                report_end_date=date(2026, 8, 4),
                calibration=make_calibration(),
                select_targets=Mock(return_value=[]),
                select_history=select_history,
                select_existing_hashes=Mock(return_value=[]),
                insert_report=Mock(),
                load_artifacts=Mock(side_effect=load_test_artifacts),
            )

        self.assertEqual(summary["input_count"], 0)
        from_env.assert_not_called()
        select_history.assert_not_called()

    def test_deterministic_only_targets_do_not_create_llm_client(self):
        summary, client, insert_report, from_env, constructor = (
            run_with_lazy_client(
                [positive_row(), negative_row()],
                history=[],
            )
        )

        self.assertEqual(summary["deterministic_count"], 1)
        from_env.assert_not_called()
        constructor.assert_not_called()
        client.generate_report.assert_not_called()
        insert_report.assert_called_once()

    def test_client_is_created_at_first_llm_target_after_deterministic(self):
        rows = [
            positive_row(actual_supply_index=0),
            negative_row(actual_supply_index=0),
            positive_row(daily_document_id=11, result_id=110),
            negative_row(daily_document_id=11, result_id=111),
        ]
        summary, client, insert_report, from_env, constructor = (
            run_with_lazy_client(rows, history=history_rows())
        )

        self.assertEqual(summary["deterministic_count"], 1)
        self.assertEqual(summary["generated_count"], 1)
        from_env.assert_called_once()
        constructor.assert_called_once()
        client.generate_report.assert_called_once()
        self.assertEqual(insert_report.call_count, 2)

    def test_multiple_llm_targets_reuse_one_client(self):
        rows = [
            positive_row(),
            negative_row(),
            positive_row(daily_document_id=11, result_id=110),
            negative_row(daily_document_id=11, result_id=111),
        ]
        summary, client, _insert_report, from_env, constructor = (
            run_with_lazy_client(rows, history=history_rows())
        )

        self.assertEqual(summary["generated_count"], 2)
        from_env.assert_called_once()
        constructor.assert_called_once()
        self.assertEqual(client.generate_report.call_count, 2)

    def test_flat_rows_are_grouped_by_variant(self):
        targets = _group_latest_document_targets(
            [positive_row(), negative_row()]
        )
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["actual_supply_index"], 0.08)
        self.assertEqual(
            set(targets[0]["results_by_variant"].keys()),
            {"positive", "negative"},
        )

    def test_ready_target_with_history_calls_llm_once(self):
        summary, client, insert_report, select_targets = run_with(
            [positive_row(), negative_row()]
        )

        self.assertEqual(summary["generated_count"], 1)
        self.assertEqual(client.generate_report.call_count, 1)
        record = insert_report.call_args.kwargs["report_record"]
        self.assertEqual(record["prompt_version"], PROMPT_VERSION)
        self.assertEqual(
            record["report_schema_version"],
            REPORT_SCHEMA_VERSION,
        )
        self.assertEqual(
            record["evidence_schema_version"],
            EVIDENCE_SCHEMA_VERSION,
        )
        self.assertEqual(record["status"], "ready")
        self.assertEqual(record["report_json"]["supply_direction"], "BUY")
        self.assertIsNotNone(record["report_json"]["comment_signal_score"])
        self.assertIsNotNone(record["report_json"]["previous_signal_score"])
        self.assertEqual(
            select_targets.call_args.kwargs["artifact_schema_version"],
            ARTIFACT_SCHEMA_VERSION,
        )

    def test_llm_request_contains_no_keyword_or_comment_evidence(self):
        _summary, client, _insert_report, _ = run_with(
            [positive_row(), negative_row()]
        )
        request = client.generate_report.call_args.args[0]
        payload = request.model_dump(mode="json")

        for forbidden in (
            "key_expressions",
            "positive_contribution_keywords",
            "negative_contribution_keywords",
            "representative_comments",
            "used_comment_refs",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, payload)
                self.assertNotIn(forbidden, str(payload))

    def test_missing_history_stores_deterministic_summary(self):
        summary, client, insert_report, _ = run_with(
            [positive_row(), negative_row()],
            history=[],
        )

        self.assertEqual(summary["deterministic_count"], 1)
        client.generate_report.assert_not_called()
        record = insert_report.call_args.kwargs["report_record"]
        self.assertEqual(record["status"], "insufficient_evidence")
        self.assertEqual(
            record["report_json"]["commentary_source"],
            "deterministic",
        )
        self.assertTrue(record["report_json"]["market_commentary"])

    def test_neutral_supply_stores_deterministic_without_signal(self):
        rows = [
            positive_row(actual_supply_index=0),
            negative_row(actual_supply_index=0),
        ]
        summary, client, insert_report, _ = run_with(rows)

        self.assertEqual(summary["deterministic_count"], 1)
        client.generate_report.assert_not_called()
        record = insert_report.call_args.kwargs["report_record"]
        self.assertEqual(record["status"], "insufficient_evidence")
        self.assertEqual(record["report_json"]["supply_direction"], "NEUTRAL")
        self.assertIsNone(record["report_json"]["comment_signal_score"])
        self.assertEqual(
            record["report_json"]["signal_status"],
            "no_direction",
        )

    def test_zero_recognized_features_stores_null_signal(self):
        rows = [
            positive_row(
                recognized_feature_count=0,
                inference_status="insufficient_features",
            ),
            negative_row(),
        ]
        summary, client, insert_report, _ = run_with(rows)

        self.assertEqual(summary["deterministic_count"], 1)
        client.generate_report.assert_not_called()
        record = insert_report.call_args.kwargs["report_record"]
        self.assertIsNone(record["report_json"]["comment_signal_score"])
        self.assertIsNone(record["report_json"]["signal_level"])
        self.assertEqual(
            record["report_json"]["signal_status"],
            "insufficient_features",
        )

    def test_missing_direction_is_not_ready(self):
        summary, client, insert_report, _ = run_with([positive_row()])

        self.assertEqual(summary["not_ready_count"], 1)
        client.generate_report.assert_not_called()
        insert_report.assert_not_called()

    def test_duplicate_direction_is_failed(self):
        summary, client, insert_report, _ = run_with(
            [positive_row(), positive_row(result_id=102), negative_row()]
        )

        self.assertEqual(summary["failed_count"], 1)
        client.generate_report.assert_not_called()
        insert_report.assert_not_called()

    def test_calibration_artifact_mismatch_is_failed(self):
        rows = [
            positive_row(),
            negative_row(),
        ]
        rows[0]["artifact_id"] = 999
        summary, client, insert_report, _ = run_with(rows)

        self.assertEqual(summary["failed_count"], 1)
        client.generate_report.assert_not_called()
        insert_report.assert_not_called()

    def test_existing_same_hash_is_not_inserted_again(self):
        first_insert = Mock(return_value=1)
        first_summary, _client, _, _ = run_with(
            [positive_row(), negative_row()],
            insert_report=first_insert,
        )
        self.assertEqual(first_summary["generated_count"], 1)
        input_hash = first_insert.call_args.kwargs["report_record"][
            "input_hash"
        ]

        second_insert = Mock(return_value=2)
        summary, second_client, _, _ = run_with(
            [positive_row(), negative_row()],
            existing=[
                {
                    "input_hash": input_hash,
                    "supply_data_status": "confirmed",
                    "supply_observed_at": datetime(2026, 8, 4, 15, 30),
                }
            ],
            insert_report=second_insert,
        )

        self.assertEqual(summary["existing_count"], 1)
        second_client.generate_report.assert_not_called()
        second_insert.assert_not_called()

    def test_existing_different_hash_is_failed(self):
        summary, client, insert_report, _ = run_with(
            [positive_row(), negative_row()],
            existing=[
                {
                    "input_hash": "0" * 64,
                    "supply_data_status": "confirmed",
                    "supply_observed_at": datetime(2026, 8, 4, 15, 30),
                }
            ],
        )

        self.assertEqual(summary["failed_count"], 1)
        client.generate_report.assert_not_called()
        insert_report.assert_not_called()

    def test_estimated_report_is_updated_when_supply_becomes_confirmed(self):
        update_report = Mock(return_value=True)
        summary, client, insert_report, _ = run_with(
            [positive_row(), negative_row()],
            existing=[
                {
                    "llm_report_id": 13,
                    "input_hash": "0" * 64,
                    "supply_data_status": "estimated",
                    "supply_observed_at": datetime(2026, 8, 4, 14, 0),
                }
            ],
            update_report=update_report,
        )

        self.assertEqual(summary["updated_count"], 1)
        self.assertEqual(client.generate_report.call_count, 1)
        insert_report.assert_not_called()
        update_report.assert_called_once()
        self.assertEqual(
            update_report.call_args.kwargs["llm_report_id"],
            13,
        )

    def test_estimated_report_is_updated_for_newer_estimate(self):
        update_report = Mock(return_value=True)
        observed_at = datetime(2026, 8, 4, 15, 0)
        summary, client, insert_report, _ = run_with(
            [
                positive_row(
                    supply_data_status="estimated",
                    supply_observed_at=observed_at,
                ),
                negative_row(
                    supply_data_status="estimated",
                    supply_observed_at=observed_at,
                ),
            ],
            existing=[
                {
                    "llm_report_id": 13,
                    "input_hash": "0" * 64,
                    "supply_data_status": "estimated",
                    "supply_observed_at": datetime(2026, 8, 4, 14, 0),
                }
            ],
            update_report=update_report,
        )

        self.assertEqual(summary["updated_count"], 1)
        self.assertEqual(client.generate_report.call_count, 1)
        insert_report.assert_not_called()
        update_report.assert_called_once()

    def test_estimated_report_keeps_newer_existing_observation(self):
        update_report = Mock(return_value=True)
        observed_at = datetime(2026, 8, 4, 14, 0)
        summary, client, insert_report, _ = run_with(
            [
                positive_row(
                    supply_data_status="estimated",
                    supply_observed_at=observed_at,
                ),
                negative_row(
                    supply_data_status="estimated",
                    supply_observed_at=observed_at,
                ),
            ],
            existing=[
                {
                    "llm_report_id": 13,
                    "input_hash": "0" * 64,
                    "supply_data_status": "estimated",
                    "supply_observed_at": datetime(2026, 8, 4, 15, 0),
                }
            ],
            update_report=update_report,
        )

        self.assertEqual(summary["existing_count"], 1)
        client.generate_report.assert_not_called()
        insert_report.assert_not_called()
        update_report.assert_not_called()

    def test_equal_estimated_observation_is_idempotent(self):
        update_report = Mock(return_value=True)
        observed_at = datetime(2026, 8, 4, 14, 0)
        summary, client, insert_report, _ = run_with(
            [
                positive_row(
                    supply_data_status="estimated",
                    supply_observed_at=observed_at,
                ),
                negative_row(
                    supply_data_status="estimated",
                    supply_observed_at=observed_at,
                ),
            ],
            existing=[
                {
                    "llm_report_id": 13,
                    "input_hash": "0" * 64,
                    "supply_data_status": "estimated",
                    "supply_observed_at": observed_at,
                }
            ],
            update_report=update_report,
        )

        self.assertEqual(summary["existing_count"], 1)
        client.generate_report.assert_not_called()
        insert_report.assert_not_called()
        update_report.assert_not_called()

    def test_confirmed_report_is_not_downgraded_to_estimated(self):
        update_report = Mock(return_value=True)
        summary, client, insert_report, _ = run_with(
            [
                positive_row(supply_data_status="estimated"),
                negative_row(supply_data_status="estimated"),
            ],
            existing=[
                {
                    "llm_report_id": 13,
                    "input_hash": "0" * 64,
                    "supply_data_status": "confirmed",
                    "supply_observed_at": datetime(2026, 8, 4, 15, 30),
                }
            ],
            update_report=update_report,
        )

        self.assertEqual(summary["existing_count"], 1)
        client.generate_report.assert_not_called()
        insert_report.assert_not_called()
        update_report.assert_not_called()

    def test_client_failure_is_not_recorded_as_success(self):
        client = Mock()
        client.generate_report.side_effect = RuntimeError("LLM failed")
        summary, _, insert_report, _ = run_with(
            [positive_row(), negative_row()],
            client=client,
        )

        self.assertEqual(summary["failed_count"], 1)
        insert_report.assert_not_called()

    def test_calibration_model_version_mismatch_is_rejected(self):
        mismatched = replace(make_calibration(), model_version=5)
        with self.assertRaisesRegex(ValueError, "model_version"):
            run_pending_llm_report_generation(
                report_start_date=date(2026, 8, 4),
                report_end_date=date(2026, 8, 4),
                client=Mock(),
                provider="academy",
                model="qwen3.5-4b",
                calibration=mismatched,
                select_targets=Mock(return_value=[]),
                select_history=Mock(return_value=[]),
                select_existing_hashes=Mock(return_value=[]),
                insert_report=Mock(),
            )


if __name__ == "__main__":
    unittest.main()


class RejectedCommentaryLoggingTest(unittest.TestCase):
    """
    검증에서 걸러진 응답을 사람이 확인할 수 있는지 고정한다.

    거부 사유만으로는 규칙이 과했는지 판단할 수 없으므로 원문과 입력
    신호가 함께 남아야 한다.
    """

    def reject(self, reason: str, *, commentary=None, attempts=2):
        """
        실제 클라이언트처럼 시도마다 통보한 뒤 최종 실패로 끝낸다.

        기록은 jobs가 담당하므로 통보 경로를 그대로 흉내 내야 로그
        계약을 검증할 수 있다.
        """

        def generate_report(request, *, on_rejection=None):
            for attempt in range(1, attempts + 1):
                if on_rejection is not None:
                    on_rejection(
                        attempt=attempt,
                        commentary=commentary,
                        reason=reason,
                    )
            raise LlmReportResponseError(
                f"LLM 시장 코멘터리 응답 검증이 2회 실패했습니다: {reason}",
                rejected_commentary=commentary,
                rejection_reason=reason,
            )

        client = Mock()
        client.generate_report.side_effect = generate_report
        insert_report = Mock(return_value=1)

        with self.assertLogs(
            "pilos.jobs.generate_llm_reports",
            level="WARNING",
        ) as captured:
            summary, _, _, _ = run_with(
                [positive_row(), negative_row()],
                client=client,
                insert_report=insert_report,
            )

        return summary, insert_report, "\n".join(captured.output)

    def test_rejected_body_and_inputs_are_logged(self):
        commentary = LlmMarketCommentary(
            market_commentary=(
                "삼성전자는 개인투자자 매수 우위입니다. "
                "댓글 수급 신호는 87점으로 매우 높으며 주가 상승세가 "
                "이어지고 있습니다."
            ),
            conclusion=(
                "삼성전자는 매수 우위이며 신호가 매우 높은 수준입니다."
            ),
        )
        summary, insert_report, output = self.reject(
            "주가 방향·투자 권유·확률 표현이 포함됐습니다: 주가 상승",
            commentary=commentary,
        )

        self.assertEqual(summary["deterministic_count"], 1)
        insert_report.assert_called_once()

        # 거부된 원문 두 필드가 모두 남아야 한다.
        self.assertIn("주가 상승세가 이어지고 있습니다", output)
        self.assertIn("신호가 매우 높은 수준입니다", output)

        # 사유와 대상 식별 정보가 함께 있어야 한다.
        self.assertIn("주가 방향·투자 권유·확률", output)
        self.assertIn("stock_code=005930", output)
        self.assertIn("model_date=2026-08-04", output)

        # 규칙이 과했는지 판단하려면 입력값도 필요하다.
        self.assertIn("actual_supply_index=0.08", output)
        self.assertIn("recognized_feature_count=8", output)
        self.assertIn("supply_direction=BUY", output)

        # 시도 번호가 남아야 1차와 2차를 구분할 수 있다.
        self.assertIn("시도=1", output)
        self.assertIn("시도=2", output)

    def test_first_attempt_is_kept_when_retry_succeeds(self):
        """재시도로 성공해도 1차에서 걸러진 원문은 남아야 한다."""
        rejected = LlmMarketCommentary(
            market_commentary=(
                "삼성전자는 개인투자자 매수 우위입니다. "
                "댓글 수급 신호는 87점으로 매우 높으며 주가 상승세가 "
                "이어지고 있습니다."
            ),
            conclusion="삼성전자 신호는 매우 높은 수준을 보이고 있습니다.",
        )
        accepted = LlmMarketCommentary(
            market_commentary=(
                "삼성전자는 오늘 개인투자자의 매수가 더 많았습니다. "
                "댓글 신호는 87점으로 매우 높은 편입니다."
            ),
            conclusion="댓글 신호는 매우 높은 수준을 이어가고 있습니다.",
        )

        def generate_report(request, *, on_rejection=None):
            if on_rejection is not None:
                on_rejection(
                    attempt=1,
                    commentary=rejected,
                    reason="주가 방향·투자 권유·확률 표현이 포함됐습니다",
                )
            return ReportGenerationResult(commentary=accepted)

        client = Mock()
        client.generate_report.side_effect = generate_report

        with self.assertLogs(
            "pilos.jobs.generate_llm_reports",
            level="WARNING",
        ) as captured:
            summary, _, _, _ = run_with(
                [positive_row(), negative_row()],
                client=client,
            )

        output = "\n".join(captured.output)

        self.assertEqual(summary["generated_count"], 1)
        self.assertEqual(summary["failed_count"], 0)
        self.assertIn("시도=1", output)
        self.assertIn("주가 상승세가 이어지고 있습니다", output)

    def test_missing_body_is_reported_without_crashing(self):
        # 파싱 단계에서 실패하면 본문이 없을 수 있다.
        summary, _, output = self.reject(
            "LLM 응답 전체를 JSON 객체로 파싱할 수 없습니다.",
            commentary=None,
        )

        self.assertEqual(summary["deterministic_count"], 1)
        self.assertIn("(본문 없음)", output)

    def test_transport_error_uses_exception_log(self):
        client = Mock()
        client.generate_report.side_effect = RuntimeError("연결 실패")

        with self.assertLogs(
            "pilos.jobs.generate_llm_reports",
            level="ERROR",
        ) as captured:
            summary, _, _, _ = run_with(
                [positive_row(), negative_row()],
                client=client,
            )

        output = "\n".join(captured.output)
        self.assertEqual(summary["failed_count"], 1)
        self.assertIn("error_type=RuntimeError", output)


class LoggingConfigurationTest(unittest.TestCase):
    """핸들러 설정은 진입점에서만 이뤄져야 한다."""

    def test_module_does_not_attach_handlers_on_import(self):
        module_logger = logging.getLogger("pilos.jobs.generate_llm_reports")

        self.assertEqual(module_logger.handlers, [])

    def test_configure_logging_writes_dated_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root_logger = logging.getLogger()
            saved_handlers = list(root_logger.handlers)
            root_logger.handlers.clear()
            try:
                log_path = configure_logging(log_dir=Path(directory))
                logging.getLogger(
                    "pilos.jobs.generate_llm_reports"
                ).warning("검수용 기록")

                for handler in logging.getLogger().handlers:
                    handler.flush()

                self.assertTrue(log_path.exists())
                self.assertIn(
                    date.today().isoformat(),
                    log_path.name,
                )
                self.assertIn(
                    "검수용 기록",
                    log_path.read_text(encoding="utf-8"),
                )
            finally:
                for handler in list(logging.getLogger().handlers):
                    handler.close()
                root_logger.handlers.clear()
                root_logger.handlers.extend(saved_handlers)
