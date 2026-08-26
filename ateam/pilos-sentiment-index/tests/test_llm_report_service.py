import unittest

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from pilos.service.llm_report_service import (
    LLMReportServiceError,
    get_llm_report_for_display,
)


DISPLAY_REPORT = {
    "status": "ready",
    "commentary_source": "llm",
    "stock_code": "005930",
    "stock_name": "삼성전자",
    "model_date": "2026-08-05",
    "supply_direction": "SELL",
    "actual_supply_index": -0.02,
    "comment_signal_score": 61,
    "signal_level": "높음",
    "signal_status": "ready",
    "supply_data_status": "confirmed",
    "supply_observed_at": "2026-08-05T15:30:00",
    "signal_change": 4,
    "signal_ma5": 57,
    "comment_count": 2409,
    "market_commentary": "현재 댓글 수급 신호는 높은 편입니다.",
    "conclusion": "직전 거래일보다 4점 높습니다.",
    "notice": "투자 권고가 아닙니다.",
}


def make_report(**overrides):
    values = {
        "report_json": DISPLAY_REPORT,
        "supply_data_status": "confirmed",
        "supply_observed_at": None,
        "current_supply_data_status": "confirmed",
        "current_supply_observed_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class LLMReportDisplayContractTest(unittest.TestCase):
    @patch("pilos.service.llm_report_service.get_llm_report")
    def test_current_v13_report_is_returned_for_display(
        self,
        get_report,
    ):
        get_report.return_value = make_report()

        result = get_llm_report_for_display(
            "005930",
            date(2026, 8, 5),
        )

        self.assertEqual(
            result,
            {
                **{
                    key: value
                    for key, value in DISPLAY_REPORT.items()
                    if key not in {"supply_data_status", "supply_observed_at"}
                },
                "report_supply_data_status": "confirmed",
                "report_supply_observed_at": "2026-08-05T15:30:00",
                "current_supply_data_status": "confirmed",
                "current_supply_observed_at": None,
                "report_refresh_status": "current",
            },
        )

    @patch("pilos.service.llm_report_service.get_llm_report")
    def test_invalid_v13_payload_is_rejected(
        self,
        get_report,
    ):
        get_report.return_value = make_report(
            report_json={"stock_code": "005930"}
        )

        with self.assertRaises(LLMReportServiceError):
            get_llm_report_for_display(
                "005930",
                date(2026, 8, 5),
            )


if __name__ == "__main__":
    unittest.main()
