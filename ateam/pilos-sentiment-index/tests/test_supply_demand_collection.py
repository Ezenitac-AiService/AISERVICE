import unittest
from datetime import date, datetime

from pilos.collection.kiwoom_supply_demand import (
    INTRADAY_INVESTOR_CODES,
    collect_confirmed_supply_demand,
    collect_intraday_estimates,
)
from pilos.dto.supply_demand_dto import (
    NoTradingDataError,
    SupplyDemandCollectionError,
)


class FakeIntradayClient:
    def __init__(self, rows_by_investor_code):
        self.rows_by_investor_code = rows_by_investor_code

    def fetch_intraday_investor_rows(self, *, investor_code):
        return self.rows_by_investor_code[investor_code]


class FakeConfirmedClient:
    def __init__(self, buy_rows, sell_rows):
        self.buy_rows = buy_rows
        self.sell_rows = sell_rows

    def fetch_confirmed_chart_rows(
        self,
        *,
        stock_code,
        trade_type,
        start_date,
        end_date,
    ):
        del stock_code, start_date, end_date
        return self.buy_rows if trade_type == "1" else self.sell_rows


class IntradayCollectionTest(unittest.TestCase):
    def _rows_by_investor_code(self):
        return {
            investor_code: [
                {
                    "stk_cd": "005930",
                    "buy_qty": "100",
                    "sell_qty": "90",
                    "acc_trde_qty": str(1000 + index),
                }
            ]
            for index, investor_code in enumerate(
                INTRADAY_INVESTOR_CODES.values()
            )
        }

    def test_collects_three_investors_for_target_stock(self):
        estimates = collect_intraday_estimates(
            client=FakeIntradayClient(self._rows_by_investor_code()),
            stock_codes=["005930"],
            trade_date=date(2026, 8, 6),
            observed_at=datetime(2026, 8, 6, 15, 30),
        )

        self.assertEqual(len(estimates), 1)
        self.assertEqual(estimates[0].stock_code, "005930")
        self.assertEqual(estimates[0].foreigner_buy_volume, 100)

    def test_all_empty_is_no_trading_but_partial_empty_is_error(self):
        all_empty = {
            investor_code: []
            for investor_code in INTRADAY_INVESTOR_CODES.values()
        }
        with self.assertRaises(NoTradingDataError):
            collect_intraday_estimates(
                client=FakeIntradayClient(all_empty),
                stock_codes=["005930"],
                trade_date=date(2026, 8, 6),
                observed_at=datetime(2026, 8, 6, 15, 30),
            )

        partial = self._rows_by_investor_code()
        partial[INTRADAY_INVESTOR_CODES["institution"]] = []
        with self.assertRaises(SupplyDemandCollectionError):
            collect_intraday_estimates(
                client=FakeIntradayClient(partial),
                stock_codes=["005930"],
                trade_date=date(2026, 8, 6),
                observed_at=datetime(2026, 8, 6, 15, 30),
            )

    def test_skips_only_stock_with_missing_investor_classification(self):
        rows_by_investor_code = self._rows_by_investor_code()
        for rows in rows_by_investor_code.values():
            rows.append(
                {
                    "stk_cd": "247540",
                    "buy_qty": "80",
                    "sell_qty": "70",
                    "acc_trde_qty": "900",
                }
            )
        rows_by_investor_code[
            INTRADAY_INVESTOR_CODES["other_corporation"]
        ].pop()

        with self.assertLogs(
            "pilos.collection.kiwoom_supply_demand",
            level="WARNING",
        ) as captured_logs:
            estimates = collect_intraday_estimates(
                client=FakeIntradayClient(rows_by_investor_code),
                stock_codes=["005930", "247540"],
                trade_date=date(2026, 8, 12),
                observed_at=datetime(2026, 8, 12, 12, 0),
            )

        self.assertEqual(
            [estimate.stock_code for estimate in estimates],
            ["005930"],
        )
        self.assertIn("stock_code=247540", captured_logs.output[0])
        self.assertIn("other_corporation", captured_logs.output[0])

    def test_no_complete_target_stock_is_no_trading_data(self):
        rows_by_investor_code = self._rows_by_investor_code()
        rows_by_investor_code[
            INTRADAY_INVESTOR_CODES["other_corporation"]
        ][0]["stk_cd"] = "247540"

        with self.assertRaises(NoTradingDataError):
            collect_intraday_estimates(
                client=FakeIntradayClient(rows_by_investor_code),
                stock_codes=["005930"],
                trade_date=date(2026, 8, 12),
                observed_at=datetime(2026, 8, 12, 12, 0),
            )


class ConfirmedCollectionTest(unittest.TestCase):
    def test_normalizes_ka10060_sell_sign(self):
        values = collect_confirmed_supply_demand(
            client=FakeConfirmedClient(
                buy_rows=[{"dt": "20260805", "ind_invsr": "5067655"}],
                sell_rows=[{"dt": "20260805", "ind_invsr": "-5290376"}],
            ),
            stock_codes=["005930"],
            start_date=date(2026, 8, 5),
            end_date=date(2026, 8, 5),
            observed_at=datetime(2026, 8, 6, 14, 0),
        )

        self.assertEqual(values[0].individual_buy_volume, 5067655)
        self.assertEqual(values[0].individual_sell_volume, 5290376)

    def test_all_empty_confirmed_response_is_no_trading(self):
        with self.assertRaises(NoTradingDataError):
            collect_confirmed_supply_demand(
                client=FakeConfirmedClient([], []),
                stock_codes=["005930"],
                start_date=date(2026, 7, 25),
                end_date=date(2026, 7, 26),
                observed_at=datetime(2026, 8, 6, 14, 0),
            )


if __name__ == "__main__":
    unittest.main()
