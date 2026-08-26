import unittest
from datetime import datetime, time
from inspect import getsource
from unittest.mock import patch

from pilos.jobs.collect_supply_demand import (
    CollectionAction,
    JobReason,
    JobStatus,
    SupplyDemandJobError,
    resolve_collection_action,
    run_supply_demand_collection,
    run_supply_demand_estimate_once,
)
from pilos.storage.supply_demand_db import (
    _UPSERT_ESTIMATED_SUPPLY_DEMAND,
)
from pilos.storage.model_training_db import select_model_training_records


class CollectionActionTest(unittest.TestCase):
    def _resolve(self, value):
        return resolve_collection_action(
            now=value,
            market_open_time=time(9, 0),
            market_close_time=time(15, 30),
            final_collection_time=time(15, 50),
        )

    def test_time_boundaries(self):
        self.assertEqual(
            self._resolve(datetime(2026, 8, 8, 10, 0)),
            CollectionAction.SKIP,
        )
        self.assertEqual(
            self._resolve(datetime(2026, 8, 6, 8, 59)),
            CollectionAction.SKIP,
        )
        self.assertEqual(
            self._resolve(datetime(2026, 8, 6, 9, 0)),
            CollectionAction.ESTIMATE,
        )
        self.assertEqual(
            self._resolve(datetime(2026, 8, 6, 15, 30)),
            CollectionAction.ESTIMATE,
        )
        self.assertEqual(
            self._resolve(datetime(2026, 8, 6, 15, 31)),
            CollectionAction.SKIP,
        )
        self.assertEqual(
            self._resolve(datetime(2026, 8, 6, 15, 50)),
            CollectionAction.CONFIRM,
        )


class EstimateJobTest(unittest.TestCase):
    @patch("pilos.jobs.collect_supply_demand.get_kst_now")
    @patch("pilos.jobs.collect_supply_demand.upsert_estimated_supply_demand")
    @patch("pilos.jobs.collect_supply_demand.collect_intraday_estimates")
    @patch("pilos.jobs.collect_supply_demand._load_stock_codes")
    def test_estimate_job_only_collects_and_saves_supply_data(
        self,
        load_stock_codes,
        collect_estimates,
        upsert_estimates,
        get_kst_now,
    ):
        now = datetime(2026, 8, 6, 15, 30)
        estimate = object()
        get_kst_now.return_value = now
        load_stock_codes.return_value = ["005930"]
        collect_estimates.return_value = [estimate]
        upsert_estimates.return_value = 1

        result = run_supply_demand_estimate_once(
            observed_at=now,
            client=object(),
        )

        self.assertEqual(result.status, JobStatus.COMPLETED)
        self.assertEqual(result.reason_code, JobReason.ESTIMATE_COMPLETED)
        self.assertEqual(result.processed_count, 1)
        self.assertEqual(result.message, "")
        upsert_estimates.assert_called_once_with([estimate])

    @patch("pilos.jobs.collect_supply_demand.get_kst_now")
    @patch("pilos.jobs.collect_supply_demand.upsert_estimated_supply_demand")
    @patch("pilos.jobs.collect_supply_demand.collect_intraday_estimates")
    @patch("pilos.jobs.collect_supply_demand._load_stock_codes")
    def test_estimate_job_reports_partially_skipped_stocks(
        self,
        load_stock_codes,
        collect_estimates,
        upsert_estimates,
        get_kst_now,
    ):
        now = datetime(2026, 8, 12, 12, 0)
        estimate = object()
        get_kst_now.return_value = now
        load_stock_codes.return_value = ["005930", "247540"]
        collect_estimates.return_value = [estimate]
        upsert_estimates.return_value = 1

        result = run_supply_demand_estimate_once(
            observed_at=now,
            client=object(),
        )

        self.assertEqual(result.status, JobStatus.COMPLETED)
        self.assertEqual(result.processed_count, 1)
        self.assertIn("1개 종목", result.message)
        upsert_estimates.assert_called_once_with([estimate])

    def test_estimated_upsert_contains_confirmed_downgrade_guard(self):
        sql = str(_UPSERT_ESTIMATED_SUPPLY_DEMAND)
        self.assertIn("confirmed_supply_demand_index IS NULL", sql)
        self.assertIn("data_status = IF", sql)

    def test_training_query_is_limited_to_confirmed_supply(self):
        source = getsource(select_model_training_records)
        self.assertIn("sd.data_status = 'confirmed'", source)

    @patch("pilos.jobs.collect_supply_demand.run_supply_demand_estimate_once")
    def test_run_supply_demand_collection_graceful_fallback_on_missing_credentials(
        self,
        mock_estimate,
    ):
        mock_estimate.side_effect = ValueError("키움 App Key와 Secret Key가 필요합니다.")
        now = datetime(2026, 8, 6, 12, 0)
        result = run_supply_demand_collection(now=now)

        self.assertEqual(result.status, JobStatus.SKIPPED)
        self.assertEqual(result.reason_code, JobReason.NO_CREDENTIALS)
        self.assertEqual(result.processed_count, 0)
        self.assertIn("키움 API 인증 정보 부재", result.message)

    @patch("pilos.jobs.collect_supply_demand.run_supply_demand_confirm_once")
    def test_run_supply_demand_collection_graceful_fallback_on_api_error(
        self,
        mock_confirm,
    ):
        mock_confirm.side_effect = SupplyDemandJobError("API connection timeout")
        now = datetime(2026, 8, 6, 15, 50)
        result = run_supply_demand_collection(now=now)

        self.assertEqual(result.status, JobStatus.SKIPPED)
        self.assertEqual(result.reason_code, JobReason.API_UNAVAILABLE)
        self.assertEqual(result.processed_count, 0)
        self.assertIn("외부 API 장애", result.message)


if __name__ == "__main__":
    unittest.main()
