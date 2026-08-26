import unittest

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from pilos.service.llm_report_service import (
    LLMReportGenerationPendingError,
    LLMReportInferencePendingError,
    LLMReportNotFoundError,
    LLMReportServiceError,
    _report_refresh_status,
    get_llm_report_for_display,
)
from pilos.web.app import app


DISPLAY_REPORT = {
    "status": "ready",
    "commentary_source": "llm",
    "stock_code": "000660",
    "stock_name": "SK하이닉스",
    "model_date": "2026-08-07",
    "supply_direction": "BUY",
    "actual_supply_index": 0.1951,
    "comment_signal_score": 84,
    "signal_level": "매우 높음",
    "signal_status": "ready",
    "supply_data_status": "confirmed",
    "supply_observed_at": "2026-08-07T15:30:00",
    "report_supply_data_status": "confirmed",
    "report_supply_observed_at": "2026-08-07T15:30:00",
    "signal_change": 27,
    "signal_ma5": 50,
    "comment_count": 1830,
    "market_commentary": "현재 댓글 신호가 과거 분포보다 높은 편입니다.",
    "conclusion": "실제 개인투자자 수급과 함께 확인해야 합니다.",
    "notice": "투자 권고가 아닙니다.",
}


class LLMReportDisplayServiceTest(unittest.TestCase):
    def test_confirmed_current_supply_marks_estimated_report_refresh_pending(self):
        report = SimpleNamespace(
            supply_data_status="estimated",
            supply_observed_at=None,
            current_supply_data_status="confirmed",
            current_supply_observed_at=None,
        )

        self.assertEqual(_report_refresh_status(report), "pending")

    @patch("pilos.service.llm_report_service.get_llm_report")
    def test_converts_stored_report_to_display_contract(self, get_report):
        get_report.return_value = SimpleNamespace(
            report_json=DISPLAY_REPORT,
            supply_data_status="confirmed",
            supply_observed_at=None,
            current_supply_data_status="confirmed",
            current_supply_observed_at=None,
        )

        result = get_llm_report_for_display(
            "000660",
            date(2026, 8, 7),
        )

        self.assertEqual(
            result,
            {
                **{
                    key: value
                    for key, value in DISPLAY_REPORT.items()
                    if key not in {"supply_data_status", "supply_observed_at"}
                },
                "current_supply_data_status": "confirmed",
                "current_supply_observed_at": None,
                "report_refresh_status": "current",
            },
        )

    @patch("pilos.service.llm_report_service.get_llm_report")
    def test_invalid_stored_report_becomes_service_error(self, get_report):
        get_report.return_value = SimpleNamespace(
            report_json={"stock_code": "000660"},
            supply_data_status=None,
            supply_observed_at=None,
            current_supply_data_status=None,
            current_supply_observed_at=None,
        )

        with self.assertRaises(LLMReportServiceError):
            get_llm_report_for_display(
                "000660",
                date(2026, 8, 7),
            )


class LLMReportRouteTest(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    @patch("pilos.web.app.get_llm_report_for_display")
    def test_ready_report_is_jsonified_with_v13_contract(self, get_report):
        get_report.return_value = DISPLAY_REPORT

        response = self.client.get(
            "/api/stocks/000660/llm-reports?model_date=2026-08-07"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), DISPLAY_REPORT)
        get_report.assert_called_once_with("000660", date(2026, 8, 7))

    @patch("pilos.web.app.get_llm_report_for_display")
    def test_contract_error_is_returned_as_json_500(self, get_report):
        get_report.side_effect = LLMReportServiceError("invalid report")

        with patch.object(app.logger, "exception"):
            response = self.client.get(
                "/api/stocks/000660/llm-reports?model_date=2026-08-07"
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.get_json(),
            {
                "status": "internal_error",
                "message": "리포트를 불러오지 못했습니다.",
            },
        )

    def test_missing_model_date_is_rejected(self):
        response = self.client.get("/api/stocks/000660/llm-reports")

        self.assertEqual(response.status_code, 400)

    def test_invalid_model_date_is_rejected(self):
        response = self.client.get(
            "/api/stocks/000660/llm-reports?model_date=08-07-2026"
        )

        self.assertEqual(response.status_code, 400)

    @patch("pilos.web.app.get_llm_report_for_display")
    def test_inference_pending_keeps_http_202_contract(self, get_report):
        get_report.side_effect = LLMReportInferencePendingError("pending")

        response = self.client.get(
            "/api/stocks/000660/llm-reports?model_date=2026-08-07"
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.get_json()["status"], "inference_pending")

    @patch("pilos.web.app.get_llm_report_for_display")
    def test_report_pending_keeps_http_202_contract(self, get_report):
        get_report.side_effect = LLMReportGenerationPendingError("pending")

        response = self.client.get(
            "/api/stocks/000660/llm-reports?model_date=2026-08-07"
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.get_json()["status"], "report_pending")

    @patch("pilos.web.app.get_llm_report_for_display")
    def test_missing_report_keeps_http_404_contract(self, get_report):
        get_report.side_effect = LLMReportNotFoundError("missing")

        response = self.client.get(
            "/api/stocks/000660/llm-reports?model_date=2026-08-07"
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["status"], "not_found")


if __name__ == "__main__":
    unittest.main()
