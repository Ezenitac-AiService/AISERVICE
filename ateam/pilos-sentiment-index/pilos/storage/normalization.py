from datetime import datetime

import pandas as pd


def normalize_identifier(
    value: object,
) -> str | None:
    """결측 식별자는 보존하고, 값이 있으면 문자열로 변환한다."""
    if value is None or pd.isna(value):
        return None
    
    return str(value).strip()

def normalize_stock_code(
    stock_code: object,
) -> str | None:
    """결측값을 보존하고 종목코드를 6자리 문자열로 변환한다."""
    if stock_code is None or pd.isna(stock_code):
        return None

    normalized = (
        str(stock_code)
        .strip()
        .removeprefix("A")
    )

    if not normalized:
        return None

    return normalized.zfill(6)

def normalize_comment_datetime(
    value: str | datetime,
) -> datetime | None:
    """
    댓글 시각을 timezone-naive datetime으로 정규화한다.

    입력 시각을 이동하지 않고 timezone 정보와 초 미만 값을 제거한다.
    """

    try:
        # 이미 datetime이면 그대로 사용하고, 문자열이면 ISO 형식의 datetime으로 파싱한다
        parsed = (
            value
            if isinstance(value, datetime)
            else datetime.fromisoformat(value)
        )
    except (TypeError, ValueError):
        # 지원하지 않는 타입이거나 올바른 시각 문자열이 아니면 결측값으로 처리할 수 있도록 None을 반환한다
        return None
    # 시각은 이동하지 않고 시간대 정보와 마이크로초만 제거한다
    return parsed.replace(
        tzinfo=None,
        microsecond=0,
    )

def normalize_comment_dataframe(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    표준 댓글 DataFrame의 식별자와 시각을
    프로젝트 공통 형식으로 정규화한다.
    """
    normalized = dataframe.copy()

    normalized["comment_id"] = (
        normalized["comment_id"]
        .map(normalize_identifier)
    )
    normalized["parent_id"] = (
        normalized["parent_id"]
        .map(normalize_identifier)
    )
    normalized["stock_code"] = (
        normalized["stock_code"]
        .map(normalize_stock_code)
    )

    for column in (
        "created_at",
        "updated_at",
    ):
        normalized[column] = pd.to_datetime(
            normalized[column].map(
                normalize_comment_datetime
            ),
            errors="coerce",
        )

    return normalized