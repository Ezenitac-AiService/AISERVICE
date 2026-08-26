import unittest
from datetime import date, datetime

from pilos.analysis.supply_demand import (
    calculate_supply_demand_index,
    estimate_individual_supply_demand,
    parse_confirmed_volume,
    parse_intraday_trade_volume,
    select_estimation_base_trade_volume,
)
from pilos.dto.supply_demand_dto import (
    IntradayInvestorValue,
    SupplyDemandCalculationError,
)


class SupplyDemandIndexTest(unittest.TestCase):
    def test_index_sign_and_zero(self):
        self.assertGreater(calculate_supply_demand_index(100, 50), 0)
        self.assertLess(calculate_supply_demand_index(50, 100), 0)
        self.assertEqual(calculate_supply_demand_index(100, 100), 0)

    def test_index_rejects_empty_and_negative_volume(self):
        with self.assertRaises(SupplyDemandCalculationError):
            calculate_supply_demand_index(0, 0)
        with self.assertRaises(SupplyDemandCalculationError):
            calculate_supply_demand_index(-1, 1)

    def test_ka10060_directional_sign_is_validated(self):
        self.assertEqual(parse_confirmed_volume("+100", trade_type="1"), 100)
        self.assertEqual(parse_confirmed_volume("-90", trade_type="2"), 90)
        with self.assertRaises(SupplyDemandCalculationError):
            parse_confirmed_volume("-100", trade_type="1")
        with self.assertRaises(SupplyDemandCalculationError):
            parse_confirmed_volume("90", trade_type="2")

    def test_ka10063_double_sell_sign_is_normalized_by_field_direction(self):
        self.assertEqual(
            parse_intraday_trade_volume(
                "+248000",
                side="buy",
                field_name="buy_qty",
            ),
            248000,
        )
        self.assertEqual(
            parse_intraday_trade_volume(
                "--530000",
                side="sell",
                field_name="sell_qty",
            ),
            530000,
        )
        with self.assertRaises(SupplyDemandCalculationError):
            parse_intraday_trade_volume(
                "--248000",
                side="buy",
                field_name="buy_qty",
            )


class IntradayResidualTest(unittest.TestCase):
    def _investor_values(self):
        return {
            "foreigner": IntradayInvestorValue(
                "005930", "foreigner", 100, 110, 1000
            ),
            "institution": IntradayInvestorValue(
                "005930", "institution", 120, 130, 1002
            ),
            "other_corporation": IntradayInvestorValue(
                "005930", "other_corporation", 20, 30, 1006
            ),
        }

    def test_central_source_volume_and_gap_are_preserved(self):
        self.assertEqual(
            select_estimation_base_trade_volume([1000, 1002, 1006]),
            1002,
        )

        estimate = estimate_individual_supply_demand(
            stock_code="005930",
            trade_date=date(2026, 8, 6),
            observed_at=datetime(2026, 8, 6, 15, 30),
            investor_values=self._investor_values(),
        )

        self.assertEqual(estimate.min_source_trade_volume, 1000)
        self.assertEqual(estimate.max_source_trade_volume, 1006)
        self.assertEqual(estimate.source_trade_volume_gap, 6)
        self.assertAlmostEqual(estimate.source_trade_volume_gap_ratio, 6 / 1006)
        self.assertEqual(estimate.estimation_base_trade_volume, 1002)
        self.assertEqual(estimate.individual_buy_volume, 762)
        self.assertEqual(estimate.individual_sell_volume, 732)

    def test_missing_investor_and_negative_residual_are_rejected(self):
        values = self._investor_values()
        values.pop("institution")
        with self.assertRaises(SupplyDemandCalculationError):
            estimate_individual_supply_demand(
                stock_code="005930",
                trade_date=date(2026, 8, 6),
                observed_at=datetime(2026, 8, 6, 15, 30),
                investor_values=values,
            )

        values = self._investor_values()
        values["foreigner"] = IntradayInvestorValue(
            "005930", "foreigner", 2000, 110, 1000
        )
        with self.assertRaisesRegex(
            SupplyDemandCalculationError,
            "추정 개인 매수량이 음수",
        ):
            estimate_individual_supply_demand(
                stock_code="005930",
                trade_date=date(2026, 8, 6),
                observed_at=datetime(2026, 8, 6, 15, 30),
                investor_values=values,
            )


if __name__ == "__main__":
    unittest.main()
