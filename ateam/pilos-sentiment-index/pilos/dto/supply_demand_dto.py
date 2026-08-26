from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


class SupplyDemandJobError(RuntimeError):
    """수급 작업의 공개 오류 기본형."""


class SupplyDemandCollectionError(SupplyDemandJobError):
    """키움 API 수집 오류."""


class SupplyDemandCalculationError(SupplyDemandJobError):
    """수급 계산·검증 오류."""


class SupplyDemandStorageError(SupplyDemandJobError):
    """수급 DB 조회·저장 오류."""


class NoTradingDataError(RuntimeError):
    """API 요청은 성공했지만 대상 거래 데이터가 없음."""


@dataclass(frozen=True, slots=True)
class IntradayInvestorValue:
    stock_code: str
    investor_type: str
    buy_volume: int
    sell_volume: int
    source_trade_volume: int


@dataclass(frozen=True, slots=True)
class EstimatedSupplyDemand:
    stock_code: str
    trade_date: date

    foreigner_buy_volume: int
    foreigner_sell_volume: int
    foreigner_source_trade_volume: int

    institution_buy_volume: int
    institution_sell_volume: int
    institution_source_trade_volume: int

    other_corporation_buy_volume: int
    other_corporation_sell_volume: int
    other_corporation_source_trade_volume: int

    min_source_trade_volume: int
    max_source_trade_volume: int
    source_trade_volume_gap: int
    source_trade_volume_gap_ratio: float
    estimation_base_trade_volume: int

    individual_buy_volume: int
    individual_sell_volume: int
    supply_demand_index: float

    observed_at: datetime
    source_api: str = "ka10063_residual"
    estimation_version: str = "kiwoom_residual_v1"


@dataclass(frozen=True, slots=True)
class ConfirmedSupplyDemand:
    stock_code: str
    trade_date: date
    individual_buy_volume: int
    individual_sell_volume: int
    supply_demand_index: float
    observed_at: datetime
    source_api: str = "ka10060"
