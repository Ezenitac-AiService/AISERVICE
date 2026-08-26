import unittest
from datetime import date, datetime
from unittest.mock import patch

from pilos.dto.keyword_contribution_dto import KeywordContributionDTO
from pilos.dto.model_result_dto import ModelResultDTO
from pilos.dto.sentiment_index_dto import SentimentIndexDTO
from pilos.service.sentiment_index_service import _analysis_status
from pilos.web.app import app


def _model(status: str | None, artifact_id: int) -> ModelResultDTO:
    return ModelResultDTO(
        artifact_id=artifact_id,
        model_variant="positive" if artifact_id == 1 else "negative",
        supply_demand_association_score=0.1,
        intercept=0.01,
        text_score=0.09,
        comment_count_contribution=0.0,
        recognized_feature_count=4,
        unique_token_count=6,
        vocabulary_coverage=0.8,
        inference_status=status,
        positive_keywords=(
            KeywordContributionDTO(keyword="매수", contribution=0.1),
        ),
        negative_keywords=(),
    )


def _item(
    *,
    supply_index: float | None = 0.2,
    positive_status: str | None = "ready",
    negative_status: str | None = "insufficient_features",
) -> SentimentIndexDTO:
    return SentimentIndexDTO(
        stock_code="000660",
        stock_name="SK하이닉스",
        model_date=date(2026, 8, 7),
        comment_count=10,
        actual_supply_demand_index=supply_index,
        actual_buy_volume=100,
        actual_sell_volume=80,
        supply_data_status="confirmed",
        supply_observed_at=datetime(2026, 8, 7, 15, 30),
        positive_model=_model(positive_status, 1),
        negative_model=_model(negative_status, 2),
        analysis_status="ready",
    )


class SentimentStatusTest(unittest.TestCase):
    def test_positive_direction_uses_only_positive_quality(self):
        self.assertEqual(_analysis_status(_item(supply_index=0.2)), "ready")

    def test_negative_direction_uses_only_negative_quality(self):
        self.assertEqual(
            _analysis_status(_item(supply_index=-0.2)),
            "insufficient_features",
        )

    def test_legacy_null_quality_is_unknown_only_in_response(self):
        self.assertEqual(
            _analysis_status(_item(positive_status=None)),
            "unknown",
        )

    def test_zero_supply_has_no_active_direction(self):
        self.assertEqual(_analysis_status(_item(supply_index=0.0)), "no_direction")


class StockRouteContractTest(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    @patch("pilos.web.app.get_main_sentiment_indexes")
    def test_list_uses_snake_case_and_hides_internal_artifact_id(self, get_items):
        get_items.return_value = [_item()]

        response = self.client.get("/api/stocks")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()[0]
        self.assertEqual(payload["stock_code"], "000660")
        self.assertEqual(payload["analysis_status"], "ready")
        self.assertEqual(
            payload["positive_model"]["inference_status"],
            "ready",
        )
        self.assertNotIn("artifact_id", payload["positive_model"])
        self.assertNotIn("positiveModel", payload)

    @patch("pilos.web.app.get_stock_detail_sentiment_indexes")
    def test_detail_uses_snake_case(self, get_items):
        get_items.return_value = [_item()]

        response = self.client.get("/api/stocks/000660")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["stock_code"], "000660")
        self.assertEqual(payload["latest"]["supply_data_status"], "confirmed")
        self.assertNotIn("code", payload)


if __name__ == "__main__":
    unittest.main()
