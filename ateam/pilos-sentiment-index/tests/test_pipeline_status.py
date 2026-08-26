import json
import tempfile
import unittest

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from pilos.jobs import run_service_pipeline as pipeline_job
from pilos.jobs.run_service_pipeline import PipelineRunSummary
from pilos.service.pipeline_status_service import (
    PipelineStatusServiceError,
    get_latest_pipeline_status_for_display,
)
from pilos.storage.pipeline_run_db import (
    PipelineRunStorageError,
    finish_pipeline_run,
    select_latest_pipeline_run,
    start_pipeline_run,
)
from pilos.web.app import app


KST = ZoneInfo("Asia/Seoul")
STARTED_AT = datetime(2026, 8, 10, 16, 10, 13, tzinfo=KST)
FINISHED_AT = datetime(2026, 8, 10, 16, 11, 13, tzinfo=KST)


class PipelineRunStorageTest(unittest.TestCase):
    @patch("pilos.storage.pipeline_run_db.get_engine")
    def test_start_inserts_running_row(self, get_engine):
        engine = MagicMock()
        connection = engine.begin.return_value.__enter__.return_value
        connection.execute.return_value.lastrowid = 31
        get_engine.return_value = engine

        run_id = start_pipeline_run(
            target="all",
            tokenizer_version="kiwi_ver1",
            operation_start_date=date(2026, 7, 25),
            started_at=STARTED_AT,
        )

        self.assertEqual(run_id, 31)
        statement, parameters = connection.execute.call_args.args
        self.assertIn("'running'", str(statement))
        self.assertEqual(parameters["target"], "all")
        self.assertEqual(parameters["started_at"].tzinfo, None)
        self.assertEqual(json.loads(parameters["stage_summary"]), {})

    @patch("pilos.storage.pipeline_run_db.get_engine")
    def test_finish_updates_only_running_row(self, get_engine):
        engine = MagicMock()
        connection = engine.begin.return_value.__enter__.return_value
        connection.execute.return_value.rowcount = 1
        get_engine.return_value = engine

        finish_pipeline_run(
            service_pipeline_run_id=31,
            summary={
                "status": "failed",
                "finished_at": FINISHED_AT,
                "elapsed_seconds": 60.0,
                "stopped_stage": "comment_collection",
                "failure_type": "RuntimeError",
                "failure_message": "failed",
                "stages": {
                    "comment_collection": {
                        "status": "partial_failure",
                        "elapsed_seconds": 59.0,
                    }
                },
            },
        )

        statement, parameters = connection.execute.call_args.args
        sql = str(statement)
        self.assertIn("status = 'running'", sql)
        self.assertEqual(parameters["service_pipeline_run_id"], 31)
        self.assertEqual(parameters["finished_at"].tzinfo, None)
        self.assertEqual(
            json.loads(parameters["stage_summary"])[
                "comment_collection"
            ]["status"],
            "partial_failure",
        )

    @patch("pilos.storage.pipeline_run_db.get_engine")
    def test_finish_rejects_missing_running_row(self, get_engine):
        engine = MagicMock()
        connection = engine.begin.return_value.__enter__.return_value
        connection.execute.return_value.rowcount = 0
        get_engine.return_value = engine

        with self.assertRaises(PipelineRunStorageError):
            finish_pipeline_run(
                service_pipeline_run_id=31,
                summary={
                    "status": "completed",
                    "finished_at": FINISHED_AT,
                    "elapsed_seconds": 60.0,
                    "stages": {},
                },
            )

    @patch("pilos.storage.pipeline_run_db.get_engine")
    def test_select_latest_deserializes_json_and_decimal(self, get_engine):
        engine = MagicMock()
        connection = engine.connect.return_value.__enter__.return_value
        query_result = MagicMock()
        query_result.mappings.return_value.first.return_value = {
            "service_pipeline_run_id": 31,
            "status": "completed",
            "target": "all",
            "tokenizer_version": "kiwi_ver1",
            "operation_start_date": date(2026, 7, 25),
            "started_at": STARTED_AT.replace(tzinfo=None),
            "finished_at": FINISHED_AT.replace(tzinfo=None),
            "elapsed_seconds": Decimal("60.125"),
            "stopped_stage": None,
            "failure_type": None,
            "failure_message": None,
            "stage_summary": '{"comment_collection":{"status":"completed"}}',
        }
        connection.execute.return_value = query_result
        get_engine.return_value = engine

        result = select_latest_pipeline_run()

        self.assertEqual(result["elapsed_seconds"], 60.125)
        self.assertEqual(
            result["stage_summary"]["comment_collection"]["status"],
            "completed",
        )


class PipelineStatusServiceTest(unittest.TestCase):
    @patch(
        "pilos.service.pipeline_status_service.select_latest_pipeline_run"
    )
    def test_no_history_returns_not_started(self, select_latest):
        select_latest.return_value = None

        self.assertEqual(
            get_latest_pipeline_status_for_display(),
            {"status": "not_started"},
        )

    @patch(
        "pilos.service.pipeline_status_service.select_latest_pipeline_run"
    )
    def test_internal_results_and_raw_error_are_not_exposed(
        self,
        select_latest,
    ):
        select_latest.return_value = {
            "service_pipeline_run_id": 31,
            "status": "failed",
            "target": "all",
            "tokenizer_version": "kiwi_ver1",
            "operation_start_date": date(2026, 7, 25),
            "started_at": STARTED_AT.replace(tzinfo=None),
            "finished_at": FINISHED_AT.replace(tzinfo=None),
            "elapsed_seconds": 60.0,
            "stopped_stage": "comment_collection",
            "failure_type": "RuntimeError",
            "failure_message": "내부 경로와 비밀정보",
            "stage_summary": {
                "comment_collection": {
                    "status": "partial_failure",
                    "elapsed_seconds": 59.0,
                    "result": {"internal_path": "secret"},
                }
            },
        }

        result = get_latest_pipeline_status_for_display()

        self.assertEqual(result["status"], "failed")
        self.assertEqual(
            result["failure_message"],
            "파이프라인 실행 중 오류가 발생했습니다.",
        )
        self.assertNotIn(
            "result",
            result["stages"]["comment_collection"],
        )

    @patch(
        "pilos.service.pipeline_status_service.select_latest_pipeline_run",
        side_effect=PipelineRunStorageError("db failed"),
    )
    def test_storage_error_becomes_service_error(self, select_latest):
        with self.assertRaises(PipelineStatusServiceError):
            get_latest_pipeline_status_for_display()


class PipelineStatusRouteTest(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    @patch("pilos.web.app.get_latest_pipeline_status_for_display")
    def test_returns_latest_status(self, get_status):
        get_status.return_value = {"status": "running"}

        response = self.client.get("/api/pipeline/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "running"})

    @patch("pilos.web.app.get_latest_pipeline_status_for_display")
    def test_service_failure_returns_safe_500(self, get_status):
        get_status.side_effect = PipelineStatusServiceError("db failed")

        with patch.object(app.logger, "exception"):
            response = self.client.get("/api/pipeline/status")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()["status"], "internal_error")
        self.assertNotIn("db failed", response.get_data(as_text=True))


class TrackedPipelineJobTest(unittest.TestCase):
    @patch.object(pipeline_job, "finish_pipeline_run")
    @patch.object(pipeline_job, "run_service_pipeline")
    @patch.object(pipeline_job, "start_pipeline_run", return_value=31)
    def test_records_start_and_finish_around_pipeline(
        self,
        start_run,
        run_pipeline,
        finish_run,
    ):
        run_pipeline.return_value = PipelineRunSummary(
            status="completed",
            target="all",
            tokenizer_version="kiwi_ver1",
            operation_start_date=date(2026, 7, 25),
            started_at=STARTED_AT,
            finished_at=FINISHED_AT,
            elapsed_seconds=60.0,
        )

        result = pipeline_job.run_tracked_service_pipeline(now=STARTED_AT)

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.service_pipeline_run_id, 31)
        start_run.assert_called_once()
        run_pipeline.assert_called_once_with(target=None, now=STARTED_AT)
        finish_run.assert_called_once()
        self.assertEqual(
            finish_run.call_args.kwargs["service_pipeline_run_id"],
            31,
        )
        self.assertIsInstance(
            finish_run.call_args.kwargs["summary"]["finished_at"],
            datetime,
        )

    @patch.object(pipeline_job, "run_service_pipeline")
    @patch.object(
        pipeline_job,
        "start_pipeline_run",
        side_effect=PipelineRunStorageError("start failed"),
    )
    def test_start_storage_failure_prevents_pipeline(
        self,
        start_run,
        run_pipeline,
    ):
        result = pipeline_job.run_tracked_service_pipeline(now=STARTED_AT)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.stopped_stage, "pipeline_status_start")
        run_pipeline.assert_not_called()

    @patch.object(
        pipeline_job,
        "finish_pipeline_run",
        side_effect=PipelineRunStorageError("finish failed"),
    )
    @patch.object(pipeline_job, "run_service_pipeline")
    @patch.object(pipeline_job, "start_pipeline_run", return_value=31)
    def test_finish_storage_failure_makes_completed_run_fail(
        self,
        start_run,
        run_pipeline,
        finish_run,
    ):
        run_pipeline.return_value = PipelineRunSummary(
            status="completed",
            target="all",
            tokenizer_version="kiwi_ver1",
            operation_start_date=date(2026, 7, 25),
            started_at=STARTED_AT,
            finished_at=FINISHED_AT,
            elapsed_seconds=60.0,
        )

        result = pipeline_job.run_tracked_service_pipeline(now=STARTED_AT)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.stopped_stage, "pipeline_status_finish")
        self.assertIn("pipeline_status", result.stages)


class PipelineFileLoggingTest(unittest.TestCase):
    def test_pipeline_log_excludes_child_logger_records(self):
        import logging

        with tempfile.TemporaryDirectory() as directory:
            before = list(pipeline_job.logger.handlers)
            try:
                path = pipeline_job.configure_pipeline_file_logging(
                    log_dir=Path(directory),
                    now=STARTED_AT,
                )
                pipeline_job.logger.info("PIPELINE_ONLY_MARKER")
                logging.getLogger(
                    "pilos.jobs.incremental_comments"
                ).warning("CHILD_LOG_MARKER")
                for handler in pipeline_job.logger.handlers:
                    handler.flush()

                content = path.read_text(encoding="utf-8")
                self.assertIn("PIPELINE_ONLY_MARKER", content)
                self.assertNotIn("CHILD_LOG_MARKER", content)
            finally:
                for handler in list(pipeline_job.logger.handlers):
                    if handler not in before:
                        pipeline_job.logger.removeHandler(handler)
                        handler.close()


if __name__ == "__main__":
    unittest.main()
