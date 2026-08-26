from __future__ import annotations

import os
from dataclasses import asdict
from datetime import date

from dotenv import load_dotenv
from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from pilos.dto.supply_demand_dto import (
    ConfirmedSupplyDemand,
    EstimatedSupplyDemand,
    SupplyDemandStorageError,
)
from pilos.storage.db import get_engine


_SELECT_STOCK_IDS = text(
    """
    SELECT stock_id, stock_code
    FROM stock
    WHERE stock_code IN :stock_codes
    """
).bindparams(bindparam("stock_codes", expanding=True))


_SELECT_CONFIRMED_STOCK_CODES = text(
    """
    SELECT s.stock_code
    FROM supply_demand AS sd
    INNER JOIN stock AS s ON s.stock_id = sd.stock_id
    WHERE sd.trade_date = :trade_date
      AND sd.data_status = 'confirmed'
      AND sd.confirmed_supply_demand_index IS NOT NULL
      AND s.stock_code IN :stock_codes
    """
).bindparams(bindparam("stock_codes", expanding=True))

_CONFIRMED_SUPPLY_DEMAND_SELECT = """
    SELECT
        s.stock_code,
        sd.trade_date,
        sd.confirmed_individual_buy_volume
            AS individual_buy_volume,
        sd.confirmed_individual_sell_volume
            AS individual_sell_volume,
        sd.confirmed_supply_demand_index
            AS supply_demand_index,
        sd.confirmed_observed_at AS observed_at,
        sd.confirmed_source_api AS source_api
    FROM supply_demand AS sd
    INNER JOIN stock AS s
        ON s.stock_id = sd.stock_id
"""


_SELECT_CONFIRMED_SUPPLY_DEMAND = text(
    _CONFIRMED_SUPPLY_DEMAND_SELECT
    + """
    WHERE s.stock_code = :stock_code
      AND sd.trade_date = :trade_date
      AND sd.data_status = 'confirmed'
      AND sd.confirmed_individual_buy_volume IS NOT NULL
      AND sd.confirmed_individual_sell_volume IS NOT NULL
      AND sd.confirmed_supply_demand_index IS NOT NULL
      AND sd.confirmed_observed_at IS NOT NULL
      AND sd.confirmed_source_api IS NOT NULL
    LIMIT 1
    """
)


_CONFIRMED_RANK_METRIC_COLUMNS = {
    "buy_volume": "sd.confirmed_individual_buy_volume",
    "sell_volume": "sd.confirmed_individual_sell_volume",
    "supply_demand_index": "sd.confirmed_supply_demand_index",
}


_UPSERT_ESTIMATED_SUPPLY_DEMAND = text(
    """
    INSERT INTO supply_demand (
        stock_id,
        trade_date,
        buy_volume,
        sell_volume,
        supply_demand_index,
        data_status,
        observed_at,
        source_api,
        foreigner_buy_volume,
        foreigner_sell_volume,
        foreigner_source_trade_volume,
        institution_buy_volume,
        institution_sell_volume,
        institution_source_trade_volume,
        other_corporation_buy_volume,
        other_corporation_sell_volume,
        other_corporation_source_trade_volume,
        min_source_trade_volume,
        max_source_trade_volume,
        source_trade_volume_gap,
        source_trade_volume_gap_ratio,
        estimation_base_trade_volume,
        estimated_individual_buy_volume,
        estimated_individual_sell_volume,
        estimated_supply_demand_index,
        estimated_observed_at,
        estimated_source_api,
        estimation_version
    ) VALUES (
        :stock_id,
        :trade_date,
        :individual_buy_volume,
        :individual_sell_volume,
        :supply_demand_index,
        'estimated',
        :observed_at,
        :source_api,
        :foreigner_buy_volume,
        :foreigner_sell_volume,
        :foreigner_source_trade_volume,
        :institution_buy_volume,
        :institution_sell_volume,
        :institution_source_trade_volume,
        :other_corporation_buy_volume,
        :other_corporation_sell_volume,
        :other_corporation_source_trade_volume,
        :min_source_trade_volume,
        :max_source_trade_volume,
        :source_trade_volume_gap,
        :source_trade_volume_gap_ratio,
        :estimation_base_trade_volume,
        :individual_buy_volume,
        :individual_sell_volume,
        :supply_demand_index,
        :observed_at,
        :source_api,
        :estimation_version
    ) AS new
    ON DUPLICATE KEY UPDATE
        foreigner_buy_volume = new.foreigner_buy_volume,
        foreigner_sell_volume = new.foreigner_sell_volume,
        foreigner_source_trade_volume = new.foreigner_source_trade_volume,
        institution_buy_volume = new.institution_buy_volume,
        institution_sell_volume = new.institution_sell_volume,
        institution_source_trade_volume = new.institution_source_trade_volume,
        other_corporation_buy_volume = new.other_corporation_buy_volume,
        other_corporation_sell_volume = new.other_corporation_sell_volume,
        other_corporation_source_trade_volume =
            new.other_corporation_source_trade_volume,
        min_source_trade_volume = new.min_source_trade_volume,
        max_source_trade_volume = new.max_source_trade_volume,
        source_trade_volume_gap = new.source_trade_volume_gap,
        source_trade_volume_gap_ratio = new.source_trade_volume_gap_ratio,
        estimation_base_trade_volume = new.estimation_base_trade_volume,
        estimated_individual_buy_volume =
            new.estimated_individual_buy_volume,
        estimated_individual_sell_volume =
            new.estimated_individual_sell_volume,
        estimated_supply_demand_index = new.estimated_supply_demand_index,
        estimated_observed_at = new.estimated_observed_at,
        estimated_source_api = new.estimated_source_api,
        estimation_version = new.estimation_version,
        buy_volume = IF(
            supply_demand.confirmed_supply_demand_index IS NULL,
            new.estimated_individual_buy_volume,
            supply_demand.buy_volume
        ),
        sell_volume = IF(
            supply_demand.confirmed_supply_demand_index IS NULL,
            new.estimated_individual_sell_volume,
            supply_demand.sell_volume
        ),
        supply_demand_index = IF(
            supply_demand.confirmed_supply_demand_index IS NULL,
            new.estimated_supply_demand_index,
            supply_demand.supply_demand_index
        ),
        data_status = IF(
            supply_demand.confirmed_supply_demand_index IS NULL,
            'estimated',
            supply_demand.data_status
        ),
        observed_at = IF(
            supply_demand.confirmed_supply_demand_index IS NULL,
            new.estimated_observed_at,
            supply_demand.observed_at
        ),
        source_api = IF(
            supply_demand.confirmed_supply_demand_index IS NULL,
            new.estimated_source_api,
            supply_demand.source_api
        ),
        collected_at = CURRENT_TIMESTAMP
    """
)


_UPSERT_CONFIRMED_SUPPLY_DEMAND = text(
    """
    INSERT INTO supply_demand (
        stock_id,
        trade_date,
        buy_volume,
        sell_volume,
        supply_demand_index,
        data_status,
        observed_at,
        source_api,
        confirmed_individual_buy_volume,
        confirmed_individual_sell_volume,
        confirmed_supply_demand_index,
        confirmed_observed_at,
        confirmed_source_api
    ) VALUES (
        :stock_id,
        :trade_date,
        :individual_buy_volume,
        :individual_sell_volume,
        :supply_demand_index,
        'confirmed',
        :observed_at,
        :source_api,
        :individual_buy_volume,
        :individual_sell_volume,
        :supply_demand_index,
        :observed_at,
        :source_api
    ) AS new
    ON DUPLICATE KEY UPDATE
        confirmed_individual_buy_volume =
            new.confirmed_individual_buy_volume,
        confirmed_individual_sell_volume =
            new.confirmed_individual_sell_volume,
        confirmed_supply_demand_index = new.confirmed_supply_demand_index,
        confirmed_observed_at = new.confirmed_observed_at,
        confirmed_source_api = new.confirmed_source_api,
        buy_volume = new.confirmed_individual_buy_volume,
        sell_volume = new.confirmed_individual_sell_volume,
        supply_demand_index = new.confirmed_supply_demand_index,
        data_status = 'confirmed',
        observed_at = new.confirmed_observed_at,
        source_api = new.confirmed_source_api,
        collected_at = CURRENT_TIMESTAMP
    """
)


def _require_db_write_enabled() -> None:
    load_dotenv()
    enabled = os.getenv(
        "SUPPLY_DEMAND_DB_WRITE_ENABLED",
        "false",
    ).strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        raise SupplyDemandStorageError(
            "SUPPLY_DEMAND_DB_WRITE_ENABLED가 활성화되지 않았습니다."
        )


def _stock_id_by_code(
    connection: Connection,
    stock_codes: list[str],
) -> dict[str, int]:
    rows = connection.execute(
        _SELECT_STOCK_IDS,
        {"stock_codes": stock_codes},
    ).mappings().all()
    stock_ids = {
        str(row["stock_code"]).zfill(6): int(row["stock_id"])
        for row in rows
    }
    missing_codes = sorted(set(stock_codes) - set(stock_ids))
    if missing_codes:
        raise ValueError(
            "stock 테이블에 등록되지 않은 종목코드가 있습니다: "
            f"{missing_codes}"
        )
    return stock_ids


def _attach_stock_ids(
    connection: Connection,
    records: list[dict],
) -> list[dict]:
    stock_codes = sorted({str(record["stock_code"]).zfill(6) for record in records})
    stock_ids = _stock_id_by_code(connection, stock_codes)
    db_records: list[dict] = []
    for record in records:
        db_record = dict(record)
        stock_code = str(db_record.pop("stock_code")).zfill(6)
        db_record["stock_id"] = stock_ids[stock_code]
        db_records.append(db_record)
    return db_records


def select_unconfirmed_stock_codes(
    *,
    stock_codes: list[str],
    trade_date: date,
) -> list[str]:
    if not stock_codes:
        return []

    normalized_codes = sorted({str(code).zfill(6) for code in stock_codes})
    try:
        engine = get_engine()
        with engine.connect() as connection:
            _stock_id_by_code(connection, normalized_codes)
            confirmed_rows = connection.execute(
                _SELECT_CONFIRMED_STOCK_CODES,
                {
                    "trade_date": trade_date,
                    "stock_codes": normalized_codes,
                },
            ).scalars().all()
    except (SQLAlchemyError, RuntimeError, ValueError) as error:
        raise SupplyDemandStorageError(
            "미확정 수급 종목 조회에 실패했습니다."
        ) from error

    confirmed_codes = {str(code).zfill(6) for code in confirmed_rows}
    return [code for code in normalized_codes if code not in confirmed_codes]


def upsert_estimated_supply_demand(
    estimates: list[EstimatedSupplyDemand],
) -> int:
    if not estimates:
        return 0

    _require_db_write_enabled()
    records = [asdict(estimate) for estimate in estimates]
    try:
        engine = get_engine()
        with engine.begin() as connection:
            db_records = _attach_stock_ids(connection, records)
            connection.execute(_UPSERT_ESTIMATED_SUPPLY_DEMAND, db_records)
    except (SQLAlchemyError, RuntimeError, ValueError) as error:
        raise SupplyDemandStorageError(
            "장중 추정 수급 DB 적재에 실패했습니다."
        ) from error

    return len(records)


def upsert_confirmed_supply_demand(
    confirmed_values: list[ConfirmedSupplyDemand],
) -> int:
    if not confirmed_values:
        return 0

    _require_db_write_enabled()
    records = [asdict(value) for value in confirmed_values]
    try:
        engine = get_engine()
        with engine.begin() as connection:
            db_records = _attach_stock_ids(connection, records)
            connection.execute(_UPSERT_CONFIRMED_SUPPLY_DEMAND, db_records)
    except (SQLAlchemyError, RuntimeError, ValueError) as error:
        raise SupplyDemandStorageError(
            "장마감 확정 수급 DB 적재에 실패했습니다."
        ) from error

    return len(records)

def _build_confirmed_ranking_query(
    metric: str,
):
    column = _CONFIRMED_RANK_METRIC_COLUMNS.get(metric)
    if column is None:
        allowed = ", ".join(
            sorted(_CONFIRMED_RANK_METRIC_COLUMNS)
        )
        raise ValueError(
            f"허용되지 않은 수급 지표입니다: {metric}. "
            f"허용값: {allowed}"
        )

    # column은 위 허용 목록에서만 가져오므로 사용자 입력이
    # SQL 문법으로 직접 들어가지 않는다.
    return text(
        _CONFIRMED_SUPPLY_DEMAND_SELECT
        + f"""
        WHERE sd.trade_date = :trade_date
          AND sd.data_status = 'confirmed'
          AND sd.confirmed_individual_buy_volume IS NOT NULL
          AND sd.confirmed_individual_sell_volume IS NOT NULL
          AND sd.confirmed_supply_demand_index IS NOT NULL
          AND sd.confirmed_observed_at IS NOT NULL
          AND sd.confirmed_source_api IS NOT NULL
        ORDER BY {column} DESC, s.stock_code ASC
        LIMIT :limit
        """
    )

def _row_to_confirmed_supply_demand(
    row,
) -> ConfirmedSupplyDemand:
    """DB 한 행을 기존 확정 수급 DTO로 변환한다."""

    return ConfirmedSupplyDemand(
        stock_code=str(row["stock_code"]).zfill(6),
        trade_date=row["trade_date"],
        individual_buy_volume=int(
            row["individual_buy_volume"]
        ),
        individual_sell_volume=int(
            row["individual_sell_volume"]
        ),
        supply_demand_index=float(
            row["supply_demand_index"]
        ),
        observed_at=row["observed_at"],
        source_api=str(row["source_api"]),
    )


def select_confirmed_supply_demand(
    *,
    stock_code: str,
    trade_date: date,
) -> ConfirmedSupplyDemand | None:
    """종목과 거래일이 일치하는 확정 수급을 조회한다."""

    normalized_stock_code = str(stock_code).strip()

    if (
        not normalized_stock_code.isdigit()
        or len(normalized_stock_code) > 6
    ):
        raise ValueError(
            "stock_code는 최대 6자리 숫자여야 합니다."
        )

    normalized_stock_code = normalized_stock_code.zfill(6)

    try:
        engine = get_engine()
        with engine.connect() as connection:
            row = connection.execute(
                _SELECT_CONFIRMED_SUPPLY_DEMAND,
                {
                    "stock_code": normalized_stock_code,
                    "trade_date": trade_date,
                },
            ).mappings().first()

            if row is None:
                return None

            return _row_to_confirmed_supply_demand(row)

    except (
        SQLAlchemyError,
        RuntimeError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise SupplyDemandStorageError(
            "확정 수급 조회에 실패했습니다."
        ) from error


def select_confirmed_supply_demand_ranking(
    *,
    trade_date: date,
    metric: str,
    limit: int = 1,
) -> list[ConfirmedSupplyDemand]:
    """특정 거래일의 확정 수급 순위를 조회한다."""

    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not 1 <= limit <= 100
    ):
        raise ValueError(
            "limit은 1부터 100 사이의 정수여야 합니다."
        )

    # 허용되지 않은 metric은 DB 연결 전에 차단한다.
    query = _build_confirmed_ranking_query(metric)

    try:
        engine = get_engine()
        with engine.connect() as connection:
            rows = connection.execute(
                query,
                {
                    "trade_date": trade_date,
                    "limit": limit,
                },
            ).mappings().all()

            return [
                _row_to_confirmed_supply_demand(row)
                for row in rows
            ]

    except (
        SQLAlchemyError,
        RuntimeError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise SupplyDemandStorageError(
            "확정 수급 순위 조회에 실패했습니다."
        ) from error