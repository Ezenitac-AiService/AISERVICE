from collections.abc import Iterable
from datetime import date

import numpy as np
import pandas as pd


def create_month_stratified_date_groups(
    *,
    model_dates: Iterable[date],
    validation_ratio: float,
    random_seed: int,
) -> tuple[frozenset[date], frozenset[date]]:
    """
    월별 날짜 분포를 유지하는 훈련·검증 날짜 집합을 생성한다.

    입력:
    - model_dates: 두 모델 방향에서 관측된 날짜 목록이다. 같은 날짜가
      여러 번 포함되어도 날짜 하나로 중복 제거한다.
    - validation_ratio: 각 월의 고유 날짜 중 검증에 배정할 비율이다.
      0보다 크고 1보다 작아야 한다.
    - random_seed: 날짜 선택을 재현하기 위한 난수 시드다.

    출력:
    - 첫 번째 frozenset은 훈련 날짜, 두 번째 frozenset은 검증 날짜다.
    - 한 월에 날짜가 하나뿐이면 그 날짜는 훈련에만 배정한다.
    - 한 월에 날짜가 둘 이상이면 훈련과 검증에 날짜가 최소 하나씩
      남도록 검증 날짜 수를 보정한다.

    같은 날짜의 여러 종목 행을 행 단위로 섞지 않고 날짜 단위로
    분리함으로써 같은 날의 수급 정보가 양쪽에 동시에 들어가는 것을
    방지한다.
    """
    if not 0 < validation_ratio < 1:
        raise ValueError(
            "validation_ratio는 0보다 크고 1보다 작아야 합니다."
        )

    if not isinstance(random_seed, int) or isinstance(random_seed, bool):
        raise ValueError(
            "random_seed는 정수여야 합니다."
        )

    date_values = list(model_dates)

    if not date_values:
        raise ValueError(
            "분할할 model_dates가 비어 있습니다."
        )

    parsed_dates = pd.to_datetime(
        pd.Series(date_values),
        errors="raise",
    )

    if parsed_dates.isna().any():
        raise ValueError(
            "model_dates에 결측 날짜가 있습니다."
        )

    unique_dates = sorted(
        set(parsed_dates.dt.date.tolist())
    )
    monthly_dates: dict[tuple[int, int], list[date]] = {}

    for model_date in unique_dates:
        month_key = (
            model_date.year,
            model_date.month,
        )
        monthly_dates.setdefault(
            month_key,
            [],
        ).append(model_date)

    random_generator = np.random.default_rng(
        random_seed
    )
    train_dates: set[date] = set()
    validation_dates: set[date] = set()

    for month_key in sorted(monthly_dates):
        dates_in_month = monthly_dates[month_key]

        if len(dates_in_month) == 1:
            train_dates.add(dates_in_month[0])
            continue

        validation_date_count = int(
            round(
                len(dates_in_month)
                * validation_ratio
            )
        )
        validation_date_count = min(
            max(validation_date_count, 1),
            len(dates_in_month) - 1,
        )

        shuffled_dates = random_generator.permutation(
            np.asarray(
                dates_in_month,
                dtype=object,
            )
        ).tolist()
        validation_dates.update(
            shuffled_dates[:validation_date_count]
        )
        train_dates.update(
            shuffled_dates[validation_date_count:]
        )

    if not train_dates:
        raise ValueError(
            "날짜 분할 결과 훈련 날짜가 비어 있습니다."
        )

    if not validation_dates:
        raise ValueError(
            "날짜 분할 결과 검증 날짜가 비어 있습니다."
        )

    if train_dates & validation_dates:
        raise RuntimeError(
            "훈련 날짜와 검증 날짜가 중복되었습니다."
        )

    if train_dates | validation_dates != set(unique_dates):
        raise RuntimeError(
            "날짜 분할 과정에서 누락된 날짜가 있습니다."
        )

    return (
        frozenset(train_dates),
        frozenset(validation_dates),
    )


def split_dataset_by_date_groups(
    *,
    dataset: pd.DataFrame,
    train_dates: frozenset[date],
    validation_dates: frozenset[date],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    전달받은 날짜 집합에 따라 한 방향의 Dataset을 두 부분으로 나눈다.

    입력:
    - dataset: model_date 컬럼을 가진 일별 모델 학습 DataFrame이다.
    - train_dates: 훈련에 사용할 고유 날짜 집합이다.
    - validation_dates: 검증에 사용할 고유 날짜 집합이다.

    출력:
    - 첫 번째 DataFrame은 훈련 행, 두 번째 DataFrame은 검증 행이다.
    - 반환 DataFrame의 model_date는 datetime.date로 정규화된다.

    훈련·검증 날짜가 겹치거나 Dataset의 날짜가 어느 집합에도 속하지
    않으면 오류를 발생시켜 분할 누락과 날짜 누출을 조기에 발견한다.
    """
    if "model_date" not in dataset.columns:
        raise ValueError(
            "Dataset에 model_date 컬럼이 없습니다."
        )

    if not train_dates:
        raise ValueError(
            "train_dates가 비어 있습니다."
        )

    if not validation_dates:
        raise ValueError(
            "validation_dates가 비어 있습니다."
        )

    if train_dates & validation_dates:
        raise ValueError(
            "train_dates와 validation_dates가 중복되었습니다."
        )

    normalized_dataset = dataset.copy()
    parsed_dates = pd.to_datetime(
        normalized_dataset["model_date"],
        errors="raise",
    )

    if parsed_dates.isna().any():
        raise ValueError(
            "Dataset의 model_date에 결측값이 있습니다."
        )

    normalized_dataset["model_date"] = (
        parsed_dates.dt.date
    )
    dataset_dates = set(
        normalized_dataset["model_date"].unique()
    )
    unassigned_dates = dataset_dates - (
        set(train_dates) | set(validation_dates)
    )

    if unassigned_dates:
        raise ValueError(
            "훈련·검증 어느 쪽에도 배정되지 않은 날짜가 있습니다: "
            f"{sorted(unassigned_dates)}"
        )

    train_df = normalized_dataset.loc[
        normalized_dataset["model_date"].isin(
            train_dates
        )
    ].copy()
    validation_df = normalized_dataset.loc[
        normalized_dataset["model_date"].isin(
            validation_dates
        )
    ].copy()

    if train_df.empty:
        raise ValueError(
            "날짜 그룹 분할 결과 훈련 데이터가 비어 있습니다."
        )

    if validation_df.empty:
        raise ValueError(
            "날짜 그룹 분할 결과 검증 데이터가 비어 있습니다."
        )

    actual_train_dates = set(
        train_df["model_date"].unique()
    )
    actual_validation_dates = set(
        validation_df["model_date"].unique()
    )

    if actual_train_dates & actual_validation_dates:
        raise RuntimeError(
            "훈련과 검증 DataFrame에 같은 날짜가 포함되었습니다."
        )

    if len(train_df) + len(validation_df) != len(normalized_dataset):
        raise RuntimeError(
            "날짜 그룹 분할 과정에서 Dataset 행이 누락되었습니다."
        )

    return train_df, validation_df
