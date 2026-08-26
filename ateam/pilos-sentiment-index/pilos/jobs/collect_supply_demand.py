from __future__ import annotations

import argparse
import logging
import os
import time as time_module
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from pilos.collection.kiwoom_supply_demand import (
    KiwoomSupplyDemandClient,
    collect_confirmed_supply_demand,
    collect_intraday_estimates,
    create_kiwoom_supply_demand_client,
)
from pilos.dto.supply_demand_dto import (
    NoTradingDataError,
    SupplyDemandJobError,
)
from pilos.storage.supply_demand_db import (
    select_unconfirmed_stock_codes,
    upsert_confirmed_supply_demand,
    upsert_estimated_supply_demand,
)


logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

DEFAULT_STOCK_CODES = (
    "005930",
    "034020",
    "068270",
    "247540",
    "035720",
    "005490",
    "005380",
    "373220",
    "035420",
    "000660",
)


class CollectionAction(StrEnum):
    SKIP = "skip"
    ESTIMATE = "estimate"
    CONFIRM = "confirm"


class CliAction(StrEnum):
    AUTO = "auto"
    ESTIMATE = "estimate"
    CONFIRM = "confirm"
    BACKFILL = "backfill"


class JobStatus(StrEnum):
    COMPLETED = "completed"
    SKIPPED = "skipped"


class JobReason(StrEnum):
    ESTIMATE_COMPLETED = "estimate_completed"
    CONFIRM_COMPLETED = "confirm_completed"
    BACKFILL_COMPLETED = "backfill_completed"
    BEFORE_MARKET = "before_market"
    WAITING_FINAL_DATA = "waiting_final_data"
    WEEKEND = "weekend"
    NO_TRADING_DATA = "no_trading_data"
    ALREADY_CONFIRMED = "already_confirmed"
    NO_CREDENTIALS = "no_credentials"
    API_UNAVAILABLE = "api_unavailable"


@dataclass(frozen=True, slots=True)
class JobResult:
    job_name: str
    status: JobStatus
    reason_code: JobReason
    processed_count: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    trade_date: date | None = None
    data_status: str | None = None
    message: str = ""


def get_kst_now() -> datetime:
    return datetime.now(KST).replace(tzinfo=None, microsecond=0)


def _normalize_kst_datetime(value: datetime | None) -> datetime:
    if value is None:
        return get_kst_now()
    if value.tzinfo is not None:
        return value.astimezone(KST).replace(tzinfo=None, microsecond=0)
    return value.replace(microsecond=0)


def _parse_hhmmss(value: str, *, setting_name: str) -> time:
    try:
        return datetime.strptime(value, "%H%M%S").time()
    except ValueError as error:
        raise ValueError(
            f"{setting_name}은 HHMMSS 형식이어야 합니다: {value!r}"
        ) from error


def _load_market_times() -> tuple[time, time, time]:
    load_dotenv()
    return (
        _parse_hhmmss(
            os.getenv("KIWOOM_MARKET_OPEN_TIME", "090000"),
            setting_name="KIWOOM_MARKET_OPEN_TIME",
        ),
        _parse_hhmmss(
            os.getenv("KIWOOM_MARKET_CLOSE_TIME", "153000"),
            setting_name="KIWOOM_MARKET_CLOSE_TIME",
        ),
        _parse_hhmmss(
            os.getenv("KIWOOM_FINAL_COLLECTION_TIME", "155000"),
            setting_name="KIWOOM_FINAL_COLLECTION_TIME",
        ),
    )


def _load_stock_codes() -> list[str]:
    load_dotenv()
    configured = os.getenv("KIWOOM_STOCK_CODES")
    if configured is None:
        return list(DEFAULT_STOCK_CODES)
    stock_codes = [code.strip() for code in configured.split(",") if code.strip()]
    if not stock_codes:
        raise ValueError("KIWOOM_STOCK_CODES에 대상 종목이 없습니다.")
    return stock_codes


def resolve_collection_action(
    *,
    now: datetime,
    market_open_time: time,
    market_close_time: time,
    final_collection_time: time,
) -> CollectionAction:
    if now.weekday() >= 5:
        return CollectionAction.SKIP

    current_time = now.time()
    if current_time < market_open_time:
        return CollectionAction.SKIP
    if market_open_time <= current_time <= market_close_time:
        return CollectionAction.ESTIMATE
    if current_time < final_collection_time:
        return CollectionAction.SKIP
    return CollectionAction.CONFIRM


def _skip_result_for_time(
    *,
    now: datetime,
    market_open_time: time,
    final_collection_time: time,
) -> JobResult:
    if now.weekday() >= 5:
        reason = JobReason.WEEKEND
    elif now.time() < market_open_time:
        reason = JobReason.BEFORE_MARKET
    elif now.time() < final_collection_time:
        reason = JobReason.WAITING_FINAL_DATA
    else:
        raise ValueError("SKIP 시간 구간이 아닙니다.")

    return JobResult(
        job_name="collect_supply_demand",
        status=JobStatus.SKIPPED,
        reason_code=reason,
        started_at=now,
        finished_at=now,
        trade_date=now.date(),
    )


def run_supply_demand_estimate_once(
    *,
    observed_at: datetime | None = None,
    client: KiwoomSupplyDemandClient | None = None,
) -> JobResult:
    observed_at = _normalize_kst_datetime(observed_at)
    started_at = get_kst_now()
    stock_codes = _load_stock_codes()
    api_client = client or create_kiwoom_supply_demand_client()

    try:
        estimates = collect_intraday_estimates(
            client=api_client,
            stock_codes=stock_codes,
            trade_date=observed_at.date(),
            observed_at=observed_at,
        )
    except NoTradingDataError:
        return JobResult(
            job_name="collect_supply_demand",
            status=JobStatus.SKIPPED,
            reason_code=JobReason.NO_TRADING_DATA,
            processed_count=0,
            started_at=started_at,
            finished_at=get_kst_now(),
            trade_date=observed_at.date(),
        )

    skipped_count = len(stock_codes) - len(estimates)
    saved_count = upsert_estimated_supply_demand(estimates)
    return JobResult(
        job_name="collect_supply_demand",
        status=JobStatus.COMPLETED,
        reason_code=JobReason.ESTIMATE_COMPLETED,
        processed_count=saved_count,
        started_at=started_at,
        finished_at=get_kst_now(),
        trade_date=observed_at.date(),
        data_status="estimated",
        message=(
            f"ka10063 투자자 분류가 누락된 {skipped_count}개 종목을 "
            "장중 추정에서 제외했습니다."
            if skipped_count
            else ""
        ),
    )


def run_supply_demand_confirm_once(
    *,
    trade_date: date | None = None,
    observed_at: datetime | None = None,
    client: KiwoomSupplyDemandClient | None = None,
) -> JobResult:
    observed_at = _normalize_kst_datetime(observed_at)
    trade_date = trade_date or observed_at.date()
    started_at = get_kst_now()
    stock_codes = _load_stock_codes()
    unconfirmed_codes = select_unconfirmed_stock_codes(
        stock_codes=stock_codes,
        trade_date=trade_date,
    )
    if not unconfirmed_codes:
        return JobResult(
            job_name="collect_supply_demand",
            status=JobStatus.SKIPPED,
            reason_code=JobReason.ALREADY_CONFIRMED,
            processed_count=0,
            started_at=started_at,
            finished_at=get_kst_now(),
            trade_date=trade_date,
            data_status="confirmed",
        )

    load_dotenv()
    retry_count = int(os.getenv("KIWOOM_CONFIRM_RETRY_COUNT", "3"))
    retry_seconds = float(os.getenv("KIWOOM_CONFIRM_RETRY_SECONDS", "5"))
    if retry_count < 1:
        raise ValueError("KIWOOM_CONFIRM_RETRY_COUNT는 1 이상이어야 합니다.")
    if retry_seconds < 0:
        raise ValueError("KIWOOM_CONFIRM_RETRY_SECONDS는 0 이상이어야 합니다.")

    api_client = client or create_kiwoom_supply_demand_client()
    confirmed_values = None
    for attempt in range(1, retry_count + 1):
        try:
            confirmed_values = collect_confirmed_supply_demand(
                client=api_client,
                stock_codes=unconfirmed_codes,
                start_date=trade_date,
                end_date=trade_date,
                observed_at=observed_at,
            )
            break
        except NoTradingDataError:
            logger.info(
                "ka10060 확정 데이터가 비어 있습니다: 시도 %s/%s",
                attempt,
                retry_count,
            )
            if attempt < retry_count and retry_seconds:
                time_module.sleep(retry_seconds)

    if confirmed_values is None:
        return JobResult(
            job_name="collect_supply_demand",
            status=JobStatus.SKIPPED,
            reason_code=JobReason.NO_TRADING_DATA,
            processed_count=0,
            started_at=started_at,
            finished_at=get_kst_now(),
            trade_date=trade_date,
        )

    saved_count = upsert_confirmed_supply_demand(confirmed_values)
    return JobResult(
        job_name="collect_supply_demand",
        status=JobStatus.COMPLETED,
        reason_code=JobReason.CONFIRM_COMPLETED,
        processed_count=saved_count,
        started_at=started_at,
        finished_at=get_kst_now(),
        trade_date=trade_date,
        data_status="confirmed",
    )


def run_supply_demand_backfill(
    *,
    start_date: date,
    end_date: date,
    client: KiwoomSupplyDemandClient | None = None,
) -> JobResult:
    today = get_kst_now().date()
    if start_date > end_date:
        raise ValueError("백필 시작일은 종료일보다 늦을 수 없습니다.")
    if end_date >= today:
        raise ValueError("백필 종료일은 KST 기준 오늘보다 이전이어야 합니다.")

    started_at = get_kst_now()
    observed_at = started_at
    api_client = client or create_kiwoom_supply_demand_client()
    try:
        confirmed_values = collect_confirmed_supply_demand(
            client=api_client,
            stock_codes=_load_stock_codes(),
            start_date=start_date,
            end_date=end_date,
            observed_at=observed_at,
        )
    except NoTradingDataError:
        return JobResult(
            job_name="backfill_supply_demand",
            status=JobStatus.SKIPPED,
            reason_code=JobReason.NO_TRADING_DATA,
            processed_count=0,
            started_at=started_at,
            finished_at=get_kst_now(),
        )

    saved_count = upsert_confirmed_supply_demand(confirmed_values)
    return JobResult(
        job_name="backfill_supply_demand",
        status=JobStatus.COMPLETED,
        reason_code=JobReason.BACKFILL_COMPLETED,
        processed_count=saved_count,
        started_at=started_at,
        finished_at=get_kst_now(),
        data_status="confirmed",
    )


def run_supply_demand_collection(
    *,
    now: datetime | None = None,
) -> JobResult:
    now = _normalize_kst_datetime(now)
    market_open_time, market_close_time, final_collection_time = (
        _load_market_times()
    )
    action = resolve_collection_action(
        now=now,
        market_open_time=market_open_time,
        market_close_time=market_close_time,
        final_collection_time=final_collection_time,
    )
    if action == CollectionAction.SKIP:
        return _skip_result_for_time(
            now=now,
            market_open_time=market_open_time,
            final_collection_time=final_collection_time,
        )

    try:
        if action == CollectionAction.ESTIMATE:
            return run_supply_demand_estimate_once(observed_at=now)
        return run_supply_demand_confirm_once(
            trade_date=now.date(),
            observed_at=now,
        )
    except ValueError as error:
        logger.warning(
            "키움 수급 수집 설정/인증 키 부재로 작업을 건너뜁니다 (Graceful Fallback): %s",
            error,
        )
        return JobResult(
            job_name="collect_supply_demand",
            status=JobStatus.SKIPPED,
            reason_code=JobReason.NO_CREDENTIALS,
            processed_count=0,
            started_at=now,
            finished_at=get_kst_now(),
            trade_date=now.date(),
            message=f"키움 API 인증 정보 부재로 스킵: {error}",
        )
    except SupplyDemandJobError as error:
        logger.warning(
            "키움 수급 수집 외부 API 연결 장애로 작업을 건너뜁니다 (Graceful Fallback): %s",
            error,
        )
        return JobResult(
            job_name="collect_supply_demand",
            status=JobStatus.SKIPPED,
            reason_code=JobReason.API_UNAVAILABLE,
            processed_count=0,
            started_at=now,
            finished_at=get_kst_now(),
            trade_date=now.date(),
            message=f"수급 데이터 수집 외부 API 장애로 스킵: {error}",
        )
    except Exception as error:
        logger.warning(
            "키움 수급 수집 중 예외 발생으로 작업을 건너뜁니다 (Graceful Fallback): %s",
            error,
        )
        return JobResult(
            job_name="collect_supply_demand",
            status=JobStatus.SKIPPED,
            reason_code=JobReason.API_UNAVAILABLE,
            processed_count=0,
            started_at=now,
            finished_at=get_kst_now(),
            trade_date=now.date(),
            message=f"수급 데이터 수집 예외로 스킵: {error}",
        )


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"날짜는 YYYYMMDD 형식이어야 합니다: {value!r}"
        ) from error


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="키움 개인 수급 수집")
    parser.add_argument(
        "--action",
        choices=[action.value for action in CliAction],
        default=CliAction.AUTO.value,
    )
    parser.add_argument("--start-date", type=_parse_date)
    parser.add_argument("--end-date", type=_parse_date)
    args = parser.parse_args(argv)

    if args.action == CliAction.BACKFILL:
        if args.start_date is None or args.end_date is None:
            parser.error("backfill에는 --start-date와 --end-date가 필요합니다.")
    elif args.start_date is not None or args.end_date is not None:
        parser.error("날짜 인자는 backfill에서만 사용할 수 있습니다.")
    return args


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    args = parse_arguments(argv)
    try:
        if args.action == CliAction.BACKFILL:
            result = run_supply_demand_backfill(
                start_date=args.start_date,
                end_date=args.end_date,
            )
        elif args.action == CliAction.ESTIMATE:
            result = run_supply_demand_estimate_once()
        elif args.action == CliAction.CONFIRM:
            result = run_supply_demand_confirm_once()
        else:
            result = run_supply_demand_collection()
    except (SupplyDemandJobError, ValueError):
        logger.exception("수급 수집 작업 실패")
        return 1

    logger.info("수급 수집 결과: %s", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
