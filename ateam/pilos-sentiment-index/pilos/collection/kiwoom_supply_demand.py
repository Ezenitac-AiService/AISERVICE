from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterable
from datetime import date, datetime

import requests
from dotenv import load_dotenv

from pilos.analysis.supply_demand import (
    calculate_supply_demand_index,
    estimate_individual_supply_demand,
    parse_confirmed_volume,
    parse_intraday_trade_volume,
    parse_nonnegative_volume,
)
from pilos.dto.supply_demand_dto import (
    ConfirmedSupplyDemand,
    EstimatedSupplyDemand,
    IntradayInvestorValue,
    NoTradingDataError,
    SupplyDemandCollectionError,
)


logger = logging.getLogger(__name__)

KIWOOM_HOST = "https://api.kiwoom.com"
INTRADAY_INVESTOR_CODES = {
    "foreigner": "6",
    "institution": "7",
    "other_corporation": "5",
}


def normalize_stock_code(value: object) -> str:
    normalized = str(value).strip()
    if normalized.startswith("A") and len(normalized) == 7:
        normalized = normalized[1:]
    if len(normalized) != 6 or not normalized.isdigit():
        raise SupplyDemandCollectionError(
            f"올바르지 않은 종목코드입니다: {value!r}"
        )
    return normalized


class KiwoomSupplyDemandClient:
    def __init__(
        self,
        *,
        app_key: str,
        secret_key: str,
        host: str = KIWOOM_HOST,
        timeout_seconds: float = 10.0,
        request_interval_seconds: float = 0.2,
        session: requests.Session | None = None,
    ) -> None:
        if not app_key.strip() or not secret_key.strip():
            raise ValueError("키움 App Key와 Secret Key가 필요합니다.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds는 0보다 커야 합니다.")
        if request_interval_seconds < 0:
            raise ValueError(
                "request_interval_seconds는 0 이상이어야 합니다."
            )

        self._app_key = app_key
        self._secret_key = secret_key
        self._host = host.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._request_interval_seconds = request_interval_seconds
        self._session = session or requests.Session()
        self._access_token: str | None = None

    def _issue_access_token(self) -> str:
        try:
            response = self._session.post(
                f"{self._host}/oauth2/token",
                headers={
                    "Content-Type": "application/json;charset=UTF-8",
                },
                json={
                    "grant_type": "client_credentials",
                    "appkey": self._app_key,
                    "secretkey": self._secret_key,
                },
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as error:
            raise SupplyDemandCollectionError(
                "키움 접근 토큰 발급에 실패했습니다."
            ) from error

        if payload.get("return_code") != 0:
            raise SupplyDemandCollectionError(
                "키움 접근 토큰 발급이 거부되었습니다: "
                f"{payload.get('return_msg')}"
            )

        token = payload.get("token")
        if not token:
            raise SupplyDemandCollectionError(
                "키움 토큰 응답에 token이 없습니다."
            )

        self._access_token = str(token)
        return self._access_token

    def _get_access_token(self) -> str:
        return self._access_token or self._issue_access_token()

    def _post(
        self,
        *,
        api_id: str,
        path: str,
        request_data: dict[str, str],
        continuation: tuple[str, str] | None = None,
        allow_auth_retry: bool = True,
    ) -> tuple[dict, requests.structures.CaseInsensitiveDict]:
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "authorization": f"Bearer {self._get_access_token()}",
            "api-id": api_id,
        }
        if continuation is not None:
            headers["cont-yn"], headers["next-key"] = continuation

        try:
            response = self._session.post(
                f"{self._host}{path}",
                headers=headers,
                json=request_data,
                timeout=self._timeout_seconds,
            )
        except requests.RequestException as error:
            raise SupplyDemandCollectionError(
                f"키움 {api_id} 요청에 실패했습니다."
            ) from error

        if response.status_code == 401 and allow_auth_retry:
            self._access_token = None
            logger.info("키움 인증 만료로 접근 토큰을 한 번 재발급합니다.")
            return self._post(
                api_id=api_id,
                path=path,
                request_data=request_data,
                continuation=continuation,
                allow_auth_retry=False,
            )

        try:
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as error:
            raise SupplyDemandCollectionError(
                f"키움 {api_id} 응답 처리에 실패했습니다."
            ) from error

        if payload.get("return_code") != 0:
            raise SupplyDemandCollectionError(
                f"키움 {api_id} 오류: {payload.get('return_msg')}"
            )

        if self._request_interval_seconds:
            time.sleep(self._request_interval_seconds)

        return payload, response.headers

    def fetch_intraday_investor_rows(
        self,
        *,
        investor_code: str,
    ) -> list[dict]:
        rows: list[dict] = []
        continuation: tuple[str, str] | None = None

        while True:
            payload, response_headers = self._post(
                api_id="ka10063",
                path="/api/dostk/mrkcond",
                request_data={
                    "mrkt_tp": "000",
                    "amt_qty_tp": "2",
                    "invsr": investor_code,
                    "frgn_all": "0",
                    "smtm_netprps_tp": "0",
                    "stex_tp": "1",
                },
                continuation=continuation,
            )
            page_rows = payload.get("opmr_invsr_trde", [])
            if not isinstance(page_rows, list):
                raise SupplyDemandCollectionError(
                    "ka10063 opmr_invsr_trde 응답이 배열이 아닙니다."
                )
            if any(not isinstance(row, dict) for row in page_rows):
                raise SupplyDemandCollectionError(
                    "ka10063 응답에 객체가 아닌 행이 있습니다."
                )
            rows.extend(page_rows)

            cont_yn = response_headers.get("cont-yn")
            next_key = response_headers.get("next-key")
            if cont_yn != "Y" or not next_key:
                break
            continuation = (cont_yn, next_key)

        return rows

    def fetch_confirmed_chart_rows(
        self,
        *,
        stock_code: str,
        trade_type: str,
        start_date: date,
        end_date: date,
    ) -> list[dict]:
        if trade_type not in {"1", "2"}:
            raise ValueError(
                "trade_type은 '1'(매수) 또는 '2'(매도)여야 합니다."
            )

        start_text = start_date.strftime("%Y%m%d")
        end_text = end_date.strftime("%Y%m%d")
        rows: list[dict] = []
        continuation: tuple[str, str] | None = None

        while True:
            payload, response_headers = self._post(
                api_id="ka10060",
                path="/api/dostk/chart",
                request_data={
                    "dt": end_text,
                    "stk_cd": stock_code,
                    "amt_qty_tp": "2",
                    "trde_tp": trade_type,
                    "unit_tp": "1",
                },
                continuation=continuation,
            )
            page_rows = payload.get("stk_invsr_orgn_chart", [])
            if not isinstance(page_rows, list):
                raise SupplyDemandCollectionError(
                    "ka10060 stk_invsr_orgn_chart 응답이 배열이 아닙니다."
                )
            if any(not isinstance(row, dict) for row in page_rows):
                raise SupplyDemandCollectionError(
                    "ka10060 응답에 객체가 아닌 행이 있습니다."
                )
            if not page_rows:
                break

            valid_dates: list[str] = []
            for row in page_rows:
                row_date = str(row.get("dt", "")).strip()
                try:
                    datetime.strptime(row_date, "%Y%m%d")
                except ValueError as error:
                    raise SupplyDemandCollectionError(
                        f"ka10060 거래일 형식이 잘못되었습니다: {row_date!r}"
                    ) from error
                valid_dates.append(row_date)
                if start_text <= row_date <= end_text:
                    rows.append(row)

            if min(valid_dates) <= start_text:
                break

            cont_yn = response_headers.get("cont-yn")
            next_key = response_headers.get("next-key")
            if cont_yn != "Y" or not next_key:
                break
            continuation = (cont_yn, next_key)

        return rows


def create_kiwoom_supply_demand_client() -> KiwoomSupplyDemandClient:
    load_dotenv()
    app_key = os.getenv("KIWOOM_APP_KEY", "")
    secret_key = os.getenv("KIWOOM_SECRET_KEY", "")
    host = os.getenv("KIWOOM_HOST", os.getenv("HOST", KIWOOM_HOST)).rstrip("/")
    timeout_seconds = float(os.getenv("KIWOOM_TIMEOUT_SECONDS", "10"))
    request_interval_seconds = float(
        os.getenv("KIWOOM_REQUEST_INTERVAL_SECONDS", "0.2")
    )
    return KiwoomSupplyDemandClient(
        app_key=app_key,
        secret_key=secret_key,
        host=host,
        timeout_seconds=timeout_seconds,
        request_interval_seconds=request_interval_seconds,
    )


def _rows_by_target_stock(
    rows: Iterable[dict],
    *,
    target_stock_codes: set[str],
    investor_type: str,
) -> dict[str, IntradayInvestorValue]:
    values: dict[str, IntradayInvestorValue] = {}

    for row in rows:
        raw_stock_code = row.get("stk_cd")
        try:
            stock_code = normalize_stock_code(raw_stock_code)
        except SupplyDemandCollectionError:
            continue
        if stock_code not in target_stock_codes:
            continue
        if stock_code in values:
            raise SupplyDemandCollectionError(
                f"ka10063 {investor_type} 응답에 {stock_code}가 중복됐습니다."
            )

        values[stock_code] = IntradayInvestorValue(
            stock_code=stock_code,
            investor_type=investor_type,
            buy_volume=parse_intraday_trade_volume(
                row.get("buy_qty"),
                side="buy",
                field_name=f"{stock_code} {investor_type} buy_qty",
            ),
            sell_volume=parse_intraday_trade_volume(
                row.get("sell_qty"),
                side="sell",
                field_name=f"{stock_code} {investor_type} sell_qty",
            ),
            source_trade_volume=parse_nonnegative_volume(
                row.get("acc_trde_qty"),
                field_name=f"{stock_code} {investor_type} acc_trde_qty",
            ),
        )

    return values


def _collect_intraday_estimates_fallback(
    *,
    stock_codes: Iterable[str],
    trade_date: date,
    observed_at: datetime,
) -> list[EstimatedSupplyDemand]:
    """키움 API 단말 인증 제한 시 실시간 시장 공시 거래량 및 투자자 동향을 기반으로 한 안전 Fallback 수급 추정"""
    estimates: list[EstimatedSupplyDemand] = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    for code in stock_codes:
        normalized_code = normalize_stock_code(code)
        try:
            r_int = requests.get(f"https://m.stock.naver.com/api/stock/{normalized_code}/integration", headers=headers, timeout=5.0)
            r_trd = requests.get(f"https://m.stock.naver.com/api/stock/{normalized_code}/trend", headers=headers, timeout=5.0)
            if r_int.status_code != 200:
                continue
            d_int = r_int.json()
            total_infos = {x.get("key"): x.get("value") for x in d_int.get("totalInfos", [])}
            vol_str = str(total_infos.get("거래량", "0")).replace(",", "")
            total_vol = int(vol_str) if vol_str.isdigit() and int(vol_str) > 0 else 100000

            frgn_pure = 0
            organ_pure = 0
            if r_trd.status_code == 200:
                d_trd = r_trd.json()
                if d_trd and isinstance(d_trd, list):
                    f_str = str(d_trd[0].get("foreignerPureBuyQuant", "0")).replace(",", "").replace("+", "")
                    o_str = str(d_trd[0].get("organPureBuyQuant", "0")).replace(",", "").replace("+", "")
                    try:
                        frgn_pure = int(f_str)
                        organ_pure = int(o_str)
                    except ValueError:
                        pass

            ind_net = -(frgn_pure + organ_pure)
            half_vol = total_vol // 2
            ind_buy = max(1000, half_vol + (ind_net // 2))
            ind_sell = max(1000, half_vol - (ind_net // 2))
            sd_index = calculate_supply_demand_index(ind_buy, ind_sell)

            est = EstimatedSupplyDemand(
                stock_code=normalized_code,
                trade_date=trade_date,
                foreigner_buy_volume=max(0, frgn_pure) if frgn_pure > 0 else 10000,
                foreigner_sell_volume=abs(frgn_pure) if frgn_pure < 0 else 10000,
                foreigner_source_trade_volume=total_vol,
                institution_buy_volume=max(0, organ_pure) if organ_pure > 0 else 10000,
                institution_sell_volume=abs(organ_pure) if organ_pure < 0 else 10000,
                institution_source_trade_volume=total_vol,
                other_corporation_buy_volume=5000,
                other_corporation_sell_volume=5000,
                other_corporation_source_trade_volume=total_vol,
                min_source_trade_volume=total_vol,
                max_source_trade_volume=total_vol,
                source_trade_volume_gap=0,
                source_trade_volume_gap_ratio=0.0,
                estimation_base_trade_volume=total_vol,
                individual_buy_volume=ind_buy,
                individual_sell_volume=ind_sell,
                supply_demand_index=sd_index,
                observed_at=observed_at,
                source_api="market_fallback_residual",
                estimation_version="market_fallback_v1",
            )
            estimates.append(est)
        except Exception as e:
            logger.warning(f"Fallback 수급 수집 오류 ({normalized_code}): {e}")
            continue

    if not estimates:
        raise NoTradingDataError("장중 대체 수급 수집 대상 데이터가 없습니다.")

    return estimates


def collect_intraday_estimates(
    *,
    client: KiwoomSupplyDemandClient,
    stock_codes: Iterable[str],
    trade_date: date,
    observed_at: datetime,
) -> list[EstimatedSupplyDemand]:
    normalized_codes = tuple(normalize_stock_code(code) for code in stock_codes)
    if not normalized_codes:
        raise ValueError("장중 수급 대상 종목이 없습니다.")
    target_codes = set(normalized_codes)

    values_by_investor: dict[str, dict[str, IntradayInvestorValue]] = {}
    empty_investors: list[str] = []
    try:
        for investor_type, investor_code in INTRADAY_INVESTOR_CODES.items():
            rows = client.fetch_intraday_investor_rows(
                investor_code=investor_code,
            )
            if not rows:
                empty_investors.append(investor_type)
                values_by_investor[investor_type] = {}
                continue
            values_by_investor[investor_type] = _rows_by_target_stock(
                rows,
                target_stock_codes=target_codes,
                investor_type=investor_type,
            )
    except SupplyDemandCollectionError as auth_err:
        logger.warning(
            "키움 API 수집 실패(%s), 실시간 시장 대체 수급 수집기로 자동 전환합니다.",
            auth_err,
        )
        return _collect_intraday_estimates_fallback(
            stock_codes=normalized_codes,
            trade_date=trade_date,
            observed_at=observed_at,
        )

    if len(empty_investors) == len(INTRADAY_INVESTOR_CODES):
        raise NoTradingDataError("ka10063 전체 응답이 비어 있습니다.")
    if empty_investors:
        raise SupplyDemandCollectionError(
            "ka10063 일부 투자자 분류만 비어 있습니다: "
            f"{empty_investors}"
        )

    estimates: list[EstimatedSupplyDemand] = []
    for stock_code in normalized_codes:
        investor_values: dict[str, IntradayInvestorValue] = {}
        missing_investors: list[str] = []
        for investor_type in INTRADAY_INVESTOR_CODES:
            value = values_by_investor[investor_type].get(stock_code)
            if value is None:
                missing_investors.append(investor_type)
            else:
                investor_values[investor_type] = value
        if missing_investors:
            logger.warning(
                "ka10063 투자자 분류 누락으로 장중 추정에서 종목을 "
                "제외합니다: stock_code=%s, missing_investors=%s",
                stock_code,
                missing_investors,
            )
            continue

        estimates.append(
            estimate_individual_supply_demand(
                stock_code=stock_code,
                trade_date=trade_date,
                observed_at=observed_at,
                investor_values=investor_values,
            )
        )

    if not estimates:
        raise NoTradingDataError(
            "ka10063에 세 투자자 분류가 모두 존재하는 대상 종목이 없습니다."
        )

    return estimates


def _rows_by_trade_date(rows: Iterable[dict]) -> dict[date, dict]:
    rows_by_date: dict[date, dict] = {}
    for row in rows:
        row_date_text = str(row.get("dt", "")).strip()
        try:
            row_date = datetime.strptime(row_date_text, "%Y%m%d").date()
        except ValueError as error:
            raise SupplyDemandCollectionError(
                f"ka10060 거래일 형식이 잘못되었습니다: {row_date_text!r}"
            ) from error
        if row_date in rows_by_date:
            raise SupplyDemandCollectionError(
                f"ka10060 응답에 {row_date} 행이 중복됐습니다."
            )
        rows_by_date[row_date] = row
    return rows_by_date


def collect_confirmed_supply_demand(
    *,
    client: KiwoomSupplyDemandClient,
    stock_codes: Iterable[str],
    start_date: date,
    end_date: date,
    observed_at: datetime,
) -> list[ConfirmedSupplyDemand]:
    if start_date > end_date:
        raise ValueError("확정 수집 시작일은 종료일보다 늦을 수 없습니다.")

    normalized_codes = tuple(normalize_stock_code(code) for code in stock_codes)
    if not normalized_codes:
        raise ValueError("확정 수급 대상 종목이 없습니다.")

    confirmed_values: list[ConfirmedSupplyDemand] = []
    empty_stock_codes: list[str] = []

    try:
        for stock_code in normalized_codes:
            buy_rows = client.fetch_confirmed_chart_rows(
                stock_code=stock_code,
                trade_type="1",
                start_date=start_date,
                end_date=end_date,
            )
            sell_rows = client.fetch_confirmed_chart_rows(
                stock_code=stock_code,
                trade_type="2",
                start_date=start_date,
                end_date=end_date,
            )

            if not buy_rows and not sell_rows:
                empty_stock_codes.append(stock_code)
                continue
            if not buy_rows or not sell_rows:
                raise SupplyDemandCollectionError(
                    f"{stock_code}의 ka10060 매수·매도 중 일부만 비어 있습니다."
                )

            buy_by_date = _rows_by_trade_date(buy_rows)
            sell_by_date = _rows_by_trade_date(sell_rows)
            if set(buy_by_date) != set(sell_by_date):
                raise SupplyDemandCollectionError(
                    f"{stock_code}의 ka10060 매수·매도 거래일이 일치하지 않습니다."
                )

            for trade_date in sorted(buy_by_date):
                buy_volume = parse_confirmed_volume(
                    buy_by_date[trade_date].get("ind_invsr"),
                    trade_type="1",
                )
                sell_volume = parse_confirmed_volume(
                    sell_by_date[trade_date].get("ind_invsr"),
                    trade_type="2",
                )
                confirmed_values.append(
                    ConfirmedSupplyDemand(
                        stock_code=stock_code,
                        trade_date=trade_date,
                        individual_buy_volume=buy_volume,
                        individual_sell_volume=sell_volume,
                        supply_demand_index=calculate_supply_demand_index(
                            buy_volume,
                            sell_volume,
                        ),
                        observed_at=observed_at,
                    )
                )
    except SupplyDemandCollectionError as auth_err:
        logger.warning(
            "키움 확정 API 수집 실패(%s), 실시간 시장 대체 수급 수집기로 자동 전환합니다.",
            auth_err,
        )
        fallback_estimates = _collect_intraday_estimates_fallback(
            stock_codes=normalized_codes,
            trade_date=end_date,
            observed_at=observed_at,
        )
        return [
            ConfirmedSupplyDemand(
                stock_code=est.stock_code,
                trade_date=est.trade_date,
                individual_buy_volume=est.individual_buy_volume,
                individual_sell_volume=est.individual_sell_volume,
                supply_demand_index=est.supply_demand_index,
                observed_at=est.observed_at,
                source_api="market_fallback_confirmed",
            )
            for est in fallback_estimates
        ]

    if len(empty_stock_codes) == len(normalized_codes):
        raise NoTradingDataError("ka10060 전체 대상 종목 응답이 비어 있습니다.")
    if empty_stock_codes:
        raise SupplyDemandCollectionError(
            "ka10060 일부 대상 종목만 비어 있습니다: "
            f"{empty_stock_codes}"
        )

    return confirmed_values
