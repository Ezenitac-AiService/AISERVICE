import os
import unittest

from datetime import date, datetime
from unittest.mock import MagicMock, patch

from pilos.dto.supply_demand_dto import (
    ConfirmedSupplyDemand,
    SupplyDemandStorageError,
)
from pilos.storage.supply_demand_db import (
    _require_db_write_enabled,
    select_confirmed_supply_demand,
    select_confirmed_supply_demand_ranking,
)


_CONFIRMED_ROW = {
    "stock_code": "005930",
    "trade_date": date(2026, 8, 5),
    "individual_buy_volume": 1500,
    "individual_sell_volume": 1000,
    "supply_demand_index": 0.2,
    "observed_at": datetime(2026, 8, 5, 16, 0),
    "source_api": "ka10060",
}


class SupplyDemandStorageGuardTest(unittest.TestCase):
    def test_write_guard_rejects_disabled_setting(self):
        with patch.dict(
            os.environ,
            {"SUPPLY_DEMAND_DB_WRITE_ENABLED": "false"},
        ):
            with self.assertRaises(
                SupplyDemandStorageError
            ):
                _require_db_write_enabled()

    def test_write_guard_accepts_enabled_setting(self):
        with patch.dict(
            os.environ,
            {"SUPPLY_DEMAND_DB_WRITE_ENABLED": "true"},
        ):
            _require_db_write_enabled()


class ConfirmedSupplyDemandReadTest(unittest.TestCase):
    def test_exact_query_returns_confirmed_value(self):
        engine = MagicMock()
        connection = (
            engine.connect.return_value
            .__enter__.return_value
        )
        query_result = MagicMock()
        query_result.mappings.return_value.first.return_value = (
            _CONFIRMED_ROW
        )
        connection.execute.return_value = query_result

        with patch(
            "pilos.storage.supply_demand_db.get_engine",
            return_value=engine,
        ):
            result = select_confirmed_supply_demand(
                stock_code="5930",
                trade_date=date(2026, 8, 5),
            )

        self.assertIsInstance(
            result,
            ConfirmedSupplyDemand,
        )
        self.assertEqual(result.stock_code, "005930")
        self.assertEqual(
            result.individual_buy_volume,
            1500,
        )
        self.assertEqual(
            result.individual_sell_volume,
            1000,
        )
        self.assertEqual(
            result.supply_demand_index,
            0.2,
        )

        statement, parameters = (
            connection.execute.call_args.args
        )
        sql = str(statement)

        self.assertIn(
            "sd.data_status = 'confirmed'",
            sql,
        )
        self.assertIn(
            "sd.confirmed_individual_buy_volume",
            sql,
        )
        self.assertEqual(
            parameters["stock_code"],
            "005930",
        )

    def test_estimated_only_row_is_not_returned(self):
        engine = MagicMock()
        connection = (
            engine.connect.return_value
            .__enter__.return_value
        )
        query_result = MagicMock()
        query_result.mappings.return_value.first.return_value = None
        connection.execute.return_value = query_result

        with patch(
            "pilos.storage.supply_demand_db.get_engine",
            return_value=engine,
        ):
            result = select_confirmed_supply_demand(
                stock_code="005930",
                trade_date=date(2026, 8, 5),
            )

        self.assertIsNone(result)

        statement = connection.execute.call_args.args[0]
        sql = str(statement)

        self.assertIn(
            "sd.data_status = 'confirmed'",
            sql,
        )
        self.assertNotIn(
            "estimated_individual_buy_volume",
            sql,
        )

    def test_ranking_uses_confirmed_metric(self):
        engine = MagicMock()
        connection = (
            engine.connect.return_value
            .__enter__.return_value
        )
        query_result = MagicMock()
        query_result.mappings.return_value.all.return_value = [
            _CONFIRMED_ROW
        ]
        connection.execute.return_value = query_result

        with patch(
            "pilos.storage.supply_demand_db.get_engine",
            return_value=engine,
        ):
            results = (
                select_confirmed_supply_demand_ranking(
                    trade_date=date(2026, 8, 5),
                    metric="buy_volume",
                    limit=1,
                )
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0].stock_code,
            "005930",
        )

        statement = connection.execute.call_args.args[0]
        sql = str(statement)

        self.assertIn(
            "ORDER BY "
            "sd.confirmed_individual_buy_volume DESC",
            sql,
        )
        self.assertIn(
            "sd.data_status = 'confirmed'",
            sql,
        )

    def test_unknown_metric_is_rejected_before_db_call(
        self,
    ):
        with patch(
            "pilos.storage.supply_demand_db.get_engine"
        ) as get_engine:
            with self.assertRaisesRegex(
                ValueError,
                "허용되지 않은 수급 지표",
            ):
                select_confirmed_supply_demand_ranking(
                    trade_date=date(2026, 8, 5),
                    metric=(
                        "buy_volume; DROP TABLE "
                        "supply_demand"
                    ),
                )

        get_engine.assert_not_called()

    def test_db_failure_becomes_storage_error(self):
        with patch(
            "pilos.storage.supply_demand_db.get_engine",
            side_effect=RuntimeError("DB 연결 실패"),
        ):
            with self.assertRaises(
                SupplyDemandStorageError
            ):
                select_confirmed_supply_demand(
                    stock_code="005930",
                    trade_date=date(2026, 8, 5),
                )


if __name__ == "__main__":
    unittest.main()