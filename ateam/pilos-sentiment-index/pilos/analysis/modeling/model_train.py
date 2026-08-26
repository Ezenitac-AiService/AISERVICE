from datetime import date

import numpy as np
import pandas as pd
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)

def split_labeled_dataset_by_date(
    dataset: pd.DataFrame,
    validation_start_date: date,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    지정한 날짜 이전은 훈련 데이터로,
    지정한 날짜부터는 검증 데이터로 분리한다.
    """
    # 검증 시작일 이전 행을 독립된 훈련 DataFrame으로 분리한다
    train_df = dataset.loc[
        dataset["model_date"] < validation_start_date
    ].copy()
    # 검증 시작일 당일부터의 행을 독립된 검증 DataFrame으로 분리한다
    validation_df = dataset.loc[
        dataset["model_date"] >= validation_start_date
    ].copy()

    if train_df.empty:
        raise ValueError("훈련 데이터가 비어 있습니다.")

    if validation_df.empty:
        raise ValueError("검증 데이터가 비어 있습니다.")

    return train_df, validation_df


def create_regression_target(
    dataset: pd.DataFrame,
) -> np.ndarray:
    """
    Dataset의 수급지수를 Ridge 학습에 사용할
    1차원 실수형 목표값 배열로 변환한다.
    """
    # 목표값으로 사용할 컬럼이 존재하는지 확인한다
    if "supply_demand_index" not in dataset.columns:
        raise ValueError(
            "Dataset에 supply_demand_index 컬럼이 없습니다."
        )

    target_series = dataset[
        "supply_demand_index"
    ]

    # 결측 목표값은 모델의 정답으로 사용할 수 없다
    if target_series.isna().any():
        raise ValueError(
            "supply_demand_index에 결측값이 있습니다."
        )

    # 문자열 등 숫자로 변환할 수 없는 값이 있으면
    # 원인을 알 수 있는 오류로 변환한다
    try:
        target = pd.to_numeric(
            target_series,
            errors="raise",
        ).to_numpy(
            dtype=float,
            copy=True,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            "supply_demand_index를 실수형 목표값으로 "
            "변환할 수 없습니다."
        ) from error

    # 빈 목표값은 모델 학습이나 평가에 사용할 수 없다
    if target.size == 0:
        raise ValueError(
            "회귀 목표값이 비어 있습니다."
        )

    # 무한대는 결측값은 아니지만 모델 입력으로 사용할 수 없다
    if not np.isfinite(target).all():
        raise ValueError(
            "supply_demand_index에 유한하지 않은 값이 있습니다."
        )

    return target

def calculate_regression_metrics(
    target: np.ndarray,
    prediction: np.ndarray,
) -> dict[str, float]:
    """
    실제 목표값과 예측값을 비교하여 회귀 평가 지표를 계산한다.
    """
    if target.shape != prediction.shape:
        raise ValueError(
            "목표값과 예측값의 형태가 다릅니다."
        )

    if target.size == 0:
        raise ValueError(
            "평가할 목표값과 예측값이 비어 있습니다."
        )

    if not np.isfinite(target).all():
        raise ValueError(
            "목표값에 유한하지 않은 값이 있습니다."
        )

    if not np.isfinite(prediction).all():
        raise ValueError(
            "예측값에 유한하지 않은 값이 있습니다."
        )

    mean_squared_error_value = mean_squared_error(
        target,
        prediction,
    )

    return {
        # MAE : 각 행의 오차 절댓값을 구한 뒤 평균을 계산한다
        # 오차 = 실제값 - 예측값 MAE = |오차|의 평균
        # 오차의 방향은 제거하며 예측값이 실제값에서 얼마나 벗어났는지 수치화한다
        "mae": float(
            mean_absolute_error(
                target,
                prediction,
            )
        ),
        # RMSE : 오차를 제곱하여 평균을 계산한후 루트를 씌운다
        # 오차 = 실제값 - 예측값 RMSE =  오차^2의평균의 제곱근
        # 큰오차에 더강한 벌점을 주도록 수치화한다
        "rmse": float(
            np.sqrt(mean_squared_error_value)
        ),
        # R2 : 오차의제곱을 예측값의 평균의 제곱으로 나누것을 1에서 뺀다
        # 오차 = 실제값 - 예측값 R² = 1 - 모델의 제곱오차 합 / 평균 예측의 제곱오차 합
        # 1이면 완벽한예측
        # 0이면 실제값 평균만 예측한 것과 같은 수준
        # 음수면 실제값 평균만 예측한 것도받 성능이 낮다
        "r2": float(
            r2_score(
                target,
                prediction,
            )
        ),
    }
