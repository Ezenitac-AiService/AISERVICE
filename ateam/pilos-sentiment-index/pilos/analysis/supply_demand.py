from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime

from pilos.dto.supply_demand_dto import (
    EstimatedSupplyDemand,
    IntradayInvestorValue,
    SupplyDemandCalculationError,
)


REQUIRED_INVESTOR_TYPES = (
    "foreigner",
    "institution",
    "other_corporation",
)


def parse_nonnegative_volume(
    value: object,
    *,
    field_name: str,
) -> int:
    if value is None:
        raise SupplyDemandCalculationError(
            f"{field_name} 값이 누락되었습니다."
        )

    normalized = str(value).replace(",", "").strip()
    if not normalized:
        raise SupplyDemandCalculationError(
            f"{field_name} 값이 비어 있습니다."
        )

    try:
        parsed = int(normalized)
    except ValueError as error:
        raise SupplyDemandCalculationError(
            f"{field_name} 값을 정수로 변환할 수 없습니다: {value!r}"
        ) from error

    if parsed < 0:
        raise SupplyDemandCalculationError(
            f"{field_name} 값은 음수일 수 없습니다: {parsed}"
        )

    return parsed


def parse_intraday_trade_volume(
    value: object,
    *,
    side: str,
    field_name: str,
) -> int:
    """ka10063의 방향별 표시 부호를 검증해 수량 크기로 변환한다."""
    if side not in {"buy", "sell"}:
        raise ValueError("side는 buy 또는 sell이어야 합니다.")
    if value is None:
        raise SupplyDemandCalculationError(
            f"{field_name} 값이 누락되었습니다."
        )

    normalized = str(value).replace(",", "").strip()
    if not normalized:
        raise SupplyDemandCalculationError(
            f"{field_name} 값이 비어 있습니다."
        )

    prefix_length = len(normalized) - len(normalized.lstrip("+-"))
    prefix = normalized[:prefix_length]
    digits = normalized[prefix_length:]
    if not digits.isdigit():
        raise SupplyDemandCalculationError(
            f"{field_name} 수량 형식이 잘못되었습니다: {value!r}"
        )
    if side == "buy" and prefix not in {"", "+"}:
        raise SupplyDemandCalculationError(
            f"{field_name} 매수 부호가 예상과 다릅니다: {value!r}"
        )
    if side == "sell" and prefix not in {"", "+", "-", "--"}:
        raise SupplyDemandCalculationError(
            f"{field_name} 매도 부호가 예상과 다릅니다: {value!r}"
        )

    return int(digits)


def parse_confirmed_volume(
    value: object,
    *,
    trade_type: str,
) -> int:
    """ka10060 방향별 응답 부호를 검증하고 체결수량으로 정규화한다."""
    if trade_type not in {"1", "2"}:
        raise ValueError("trade_type은 '1'(매수) 또는 '2'(매도)여야 합니다.")

    if value is None:
        raise SupplyDemandCalculationError(
            "ka10060 ind_invsr 값이 누락되었습니다."
        )

    normalized = str(value).replace(",", "").strip()
    if not normalized:
        raise SupplyDemandCalculationError(
            "ka10060 ind_invsr 값이 비어 있습니다."
        )

    try:
        parsed = int(normalized)
    except ValueError as error:
        raise SupplyDemandCalculationError(
            f"ka10060 ind_invsr 값을 정수로 변환할 수 없습니다: {value!r}"
        ) from error

    if trade_type == "1" and parsed < 0:
        raise SupplyDemandCalculationError(
            f"ka10060 매수량의 부호가 예상과 다릅니다: {parsed}"
        )

    if trade_type == "2" and parsed > 0:
        raise SupplyDemandCalculationError(
            f"ka10060 매도량의 부호가 예상과 다릅니다: {parsed}"
        )

    return abs(parsed)


def calculate_supply_demand_index(
    buy_volume: int,
    sell_volume: int,
) -> float:
    if buy_volume < 0 or sell_volume < 0:
        raise SupplyDemandCalculationError(
            "매수량과 매도량은 음수일 수 없습니다."
        )

    total_volume = buy_volume + sell_volume
    if total_volume == 0:
        raise SupplyDemandCalculationError(
            "매수량과 매도량이 모두 0이므로 수급지수를 계산할 수 없습니다."
        )

    value = (buy_volume - sell_volume) / total_volume
    if not -1.0 <= value <= 1.0:
        raise SupplyDemandCalculationError(
            f"수급지수 범위 오류: {value}"
        )

    return value


def select_estimation_base_trade_volume(
    source_trade_volumes: Iterable[int],
) -> int:
    """네 호출의 중앙 두 누적거래량 평균을 정수 체결량으로 사용한다."""
    values = sorted(source_trade_volumes)
    if len(values) != 3:
        raise SupplyDemandCalculationError(
            "기준 거래량 선택에는 투자자 네 분류가 모두 필요합니다."
        )
    if any(value < 0 for value in values):
        raise SupplyDemandCalculationError(
            "누적거래량은 음수일 수 없습니다."
        )
    if values[-1] == 0:
        raise SupplyDemandCalculationError(
            "기준 누적거래량이 0입니다."
        )

    return values[1]


def estimate_individual_supply_demand(
    *,
    stock_code: str,
    trade_date: date,
    observed_at: datetime,
    investor_values: Mapping[str, IntradayInvestorValue],
) -> EstimatedSupplyDemand:
    missing_investors = set(REQUIRED_INVESTOR_TYPES) - set(investor_values)
    extra_investors = set(investor_values) - set(REQUIRED_INVESTOR_TYPES)
    if missing_investors or extra_investors:
        raise SupplyDemandCalculationError(
            "장중 투자자 분류가 정확하지 않습니다: "
            f"누락={sorted(missing_investors)}, 추가={sorted(extra_investors)}"
        )

    for investor_type, value in investor_values.items():
        if value.stock_code != stock_code:
            raise SupplyDemandCalculationError(
                f"{investor_type} 종목코드가 일치하지 않습니다."
            )
        if value.investor_type != investor_type:
            raise SupplyDemandCalculationError(
                f"{investor_type} 투자자 분류가 일치하지 않습니다."
            )

    source_volumes = [
        investor_values[investor_type].source_trade_volume
        for investor_type in REQUIRED_INVESTOR_TYPES
    ]
    min_source_volume = min(source_volumes)
    max_source_volume = max(source_volumes)
    source_volume_gap = max_source_volume - min_source_volume
    estimation_base_volume = select_estimation_base_trade_volume(
        source_volumes
    )
    source_volume_gap_ratio = source_volume_gap / max_source_volume

    non_individual_buy = sum(
        investor_values[investor_type].buy_volume
        for investor_type in REQUIRED_INVESTOR_TYPES
    )
    non_individual_sell = sum(
        investor_values[investor_type].sell_volume
        for investor_type in REQUIRED_INVESTOR_TYPES
    )

    individual_buy = estimation_base_volume - non_individual_buy
    individual_sell = estimation_base_volume - non_individual_sell
    if individual_buy < 0:
        raise SupplyDemandCalculationError(
            f"추정 개인 매수량이 음수입니다: {individual_buy}"
        )
    if individual_sell < 0:
        raise SupplyDemandCalculationError(
            f"추정 개인 매도량이 음수입니다: {individual_sell}"
        )

    supply_demand_index = calculate_supply_demand_index(
        individual_buy,
        individual_sell,
    )

    foreigner = investor_values["foreigner"]
    institution = investor_values["institution"]
    other_corporation = investor_values["other_corporation"]

    return EstimatedSupplyDemand(
        stock_code=stock_code,
        trade_date=trade_date,
        foreigner_buy_volume=foreigner.buy_volume,
        foreigner_sell_volume=foreigner.sell_volume,
        foreigner_source_trade_volume=foreigner.source_trade_volume,
        institution_buy_volume=institution.buy_volume,
        institution_sell_volume=institution.sell_volume,
        institution_source_trade_volume=institution.source_trade_volume,
        other_corporation_buy_volume=other_corporation.buy_volume,
        other_corporation_sell_volume=other_corporation.sell_volume,
        other_corporation_source_trade_volume=(
            other_corporation.source_trade_volume
        ),
        min_source_trade_volume=min_source_volume,
        max_source_trade_volume=max_source_volume,
        source_trade_volume_gap=source_volume_gap,
        source_trade_volume_gap_ratio=source_volume_gap_ratio,
        estimation_base_trade_volume=estimation_base_volume,
        individual_buy_volume=individual_buy,
        individual_sell_volume=individual_sell,
        supply_demand_index=supply_demand_index,
        observed_at=observed_at,
    )
