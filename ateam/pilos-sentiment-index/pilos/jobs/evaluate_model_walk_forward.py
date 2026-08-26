import logging
import sys

from datetime import date
from typing import Literal

import numpy as np
import pandas as pd

from sklearn.linear_model import (
    ElasticNet,
    Ridge,
)

from pilos.analysis.modeling.elastic_net_model import (
    create_elastic_net_model,
)
from pilos.analysis.modeling.model_features import (
    combine_model_features,
    fit_transform_comment_count_feature,
    transform_comment_count_feature,
)
from pilos.analysis.modeling.model_train import (
    calculate_regression_metrics,
    create_regression_target,
    split_labeled_dataset_by_date,
)
from pilos.analysis.modeling.ridge_model import (
    create_ridge_model,
)
from pilos.analysis.tokenizer_settings import (
    TOKENIZER_VERSION,
)
from pilos.analysis.vectorizer import (
    create_tfidf_vectorizer,
)
from pilos.jobs.train_model import (
    LOWERCASE,
    MAX_DF,
    MAX_FEATURES,
    MIN_DF,
    NGRAM_RANGE,
    RIDGE_ALPHA,
    RIDGE_FIT_INTERCEPT,
    RIDGE_MAX_ITER,
    RIDGE_POSITIVE,
    RIDGE_SOLVER,
    RIDGE_TOL,
    SUBLINEAR_TF,
)
from pilos.storage.model_training_db import (
    SupplyDirection,
    select_model_training_records,
)

logger = logging.getLogger(__name__)

ModelType = Literal[
    "ridge",
    "elastic_net",
]
FeatureMode = Literal[
    "text_only",
    "text_plus_comment_count",
]
LinearModel = Ridge | ElasticNet

MODEL_VARIANTS: tuple[SupplyDirection, ...] = (
    "positive",
    "negative",
)

# text_only는 TF-IDF 열만 모델 입력으로 사용한다.
# text_plus_comment_count는 TF-IDF 마지막에 표준화된 로그 댓글 수
# 특성 한 열을 추가하여 현재 정식 Ridge 학습 방식과 같은 입력을 만든다.
FEATURE_MODES: tuple[FeatureMode, ...] = (
    "text_only",
    "text_plus_comment_count",
)

# Ridge와 ElasticNet의 alpha는 서로 다른 목적함수에서 사용되므로
# 같은 숫자를 같은 규제 강도로 해석하지 않고 별도 후보 범위를 둔다.
RIDGE_EXPERIMENT_ALPHAS = (
    0.1,
    RIDGE_ALPHA,
    10.0,
    100.0,
)
ELASTIC_NET_EXPERIMENT_ALPHAS = (
    0.0001,
    0.001,
    0.01,
    0.1,
)

# l1_ratio가 커질수록 더 많은 단어 계수가 정확히 0이 될 가능성이
# 커진다. 1.0은 순수 L1 규제에 가까운 비교 후보로 사용한다.
ELASTIC_NET_EXPERIMENT_L1_RATIOS = (
    0.1,
    0.5,
    0.9,
    1.0,
)
ELASTIC_NET_MAX_ITER = 10_000
ELASTIC_NET_TOL = 1e-4
ELASTIC_NET_SELECTION = "cyclic"

# 각 Fold는 validation_start_date 이전의 모든 데이터를 학습에
# 사용하고, 시작일부터 종료일까지의 한 달 구간만 검증에 사용한다.
VALIDATION_FOLDS = (
    {
        "validation_start_date": date(2026, 4, 1),
        "validation_end_date": date(2026, 4, 30),
    },
    {
        "validation_start_date": date(2026, 5, 1),
        "validation_end_date": date(2026, 5, 31),
    },
    {
        "validation_start_date": date(2026, 6, 1),
        "validation_end_date": date(2026, 6, 30),
    },
    {
        "validation_start_date": date(2026, 7, 1),
        "validation_end_date": date(2026, 7, 24),
    },
)

EVALUATION_END_DATE = max(
    fold["validation_end_date"]
    for fold in VALIDATION_FOLDS
)

# CLI:
# uv run python -m pilos.jobs.evaluate_model_walk_forward


def create_experiment_configs() -> tuple[dict, ...]:
    """
    워크포워드에서 비교할 모델·특성·규제 조합을 생성한다.

    입력:
    - 함수 인자는 없다. 모듈 상단의 Ridge alpha, ElasticNet alpha,
      l1_ratio와 특성 모드 후보를 사용한다.

    출력:
    - 각 원소가 한 실험 후보를 나타내는 dict 튜플을 반환한다.
    - experiment_name은 발표 표와 로그에서 후보를 식별하는 이름이다.
    - model_type은 Ridge 또는 ElasticNet 생성 함수를 선택한다.
    - feature_mode는 댓글 수 특성 포함 여부를 선택한다.
    - alpha와 l1_ratio는 해당 모델을 생성할 규제 설정이다.
    """
    configs = []

    for feature_mode in FEATURE_MODES:
        for alpha in RIDGE_EXPERIMENT_ALPHAS:
            configs.append(
                {
                    "experiment_name": (
                        f"ridge__{feature_mode}__"
                        f"alpha_{alpha:g}"
                    ),
                    "model_type": "ridge",
                    "feature_mode": feature_mode,
                    "alpha": alpha,
                    "l1_ratio": None,
                }
            )

        for alpha in (
            ELASTIC_NET_EXPERIMENT_ALPHAS
        ):
            for l1_ratio in (
                ELASTIC_NET_EXPERIMENT_L1_RATIOS
            ):
                configs.append(
                    {
                        "experiment_name": (
                            "elastic_net__"
                            f"{feature_mode}__"
                            f"alpha_{alpha:g}__"
                            f"l1_{l1_ratio:g}"
                        ),
                        "model_type": "elastic_net",
                        "feature_mode": feature_mode,
                        "alpha": alpha,
                        "l1_ratio": l1_ratio,
                    }
                )

    return tuple(configs)


def create_experiment_model(
    experiment_config: dict,
) -> LinearModel:
    """
    한 실험 설정에 해당하는 학습 전 선형 회귀 모델을 생성한다.

    입력:
    - experiment_config: model_type, alpha와 ElasticNet의 경우
      l1_ratio를 포함한 실험 설정이다.

    출력:
    - model_type이 ridge면 기존 Ridge 생성 함수의 모델을 반환한다.
    - model_type이 elastic_net이면 ElasticNet 생성 함수의 모델을
      반환한다.
    - 반환 모델은 아직 fit되지 않았으며 호출자가 Fold 훈련 특성과
      목표값으로 학습해야 한다.
    """
    model_type: ModelType = experiment_config[
        "model_type"
    ]

    if model_type == "ridge":
        return create_ridge_model(
            alpha=experiment_config["alpha"],
            fit_intercept=RIDGE_FIT_INTERCEPT,
            solver=RIDGE_SOLVER,
            tol=RIDGE_TOL,
            max_iter=RIDGE_MAX_ITER,
            positive=RIDGE_POSITIVE,
        )

    if model_type == "elastic_net":
        return create_elastic_net_model(
            alpha=experiment_config["alpha"],
            l1_ratio=experiment_config[
                "l1_ratio"
            ],
            fit_intercept=RIDGE_FIT_INTERCEPT,
            max_iter=ELASTIC_NET_MAX_ITER,
            tol=ELASTIC_NET_TOL,
            selection=ELASTIC_NET_SELECTION,
        )

    raise ValueError(
        "model_type은 ridge 또는 elastic_net이어야 합니다."
    )


def prepare_model_fold(
    *,
    dataset: pd.DataFrame,
    validation_start_date: date,
    validation_end_date: date,
) -> dict:
    """
    한 날짜 Fold의 공통 훈련·검증 특성과 목표값을 준비한다.

    입력:
    - dataset: 한 수급 방향의 전체 일별 학습 레코드 DataFrame이다.
      model_date, tfidf_text, comment_count와 supply_demand_index를
      포함해야 한다.
    - validation_start_date: 이 날짜 이전 레코드는 훈련에 사용한다.
    - validation_end_date: 이 날짜를 초과하는 레코드는 현재 Fold에서
      제외하여 미래 데이터가 학습·검증에 유입되지 않게 한다.

    출력:
    - train_df와 validation_df: Fold별 원본 메타데이터와 댓글 수
      분포를 확인할 DataFrame이다.
    - train_text_features와 validation_text_features: 훈련 문서로
      학습한 Vectorizer가 생성한 TF-IDF 희소행렬이다.
    - train_combined_features와 validation_combined_features: TF-IDF
      마지막 열에 표준화된 로그 댓글 수를 추가한 희소행렬이다.
    - train_target과 validation_target: Ridge와 ElasticNet이 예측할
      수급지수 1차원 배열이다.

    같은 Fold의 모든 후보가 이 결과를 재사용하므로 모델 후보마다
    TF-IDF와 댓글 수 스케일러를 다시 학습하지 않는다.
    """
    fold_dataset = dataset.loc[
        dataset["model_date"] <= validation_end_date
    ].copy()

    train_df, validation_df = (
        split_labeled_dataset_by_date(
            fold_dataset,
            validation_start_date=validation_start_date,
        )
    )

    vectorizer = create_tfidf_vectorizer(
        lowercase=LOWERCASE,
        ngram_range=NGRAM_RANGE,
        min_df=MIN_DF,
        max_df=MAX_DF,
        max_features=MAX_FEATURES,
        sublinear_tf=SUBLINEAR_TF,
    )

    # Vectorizer와 댓글 수 Scaler는 훈련 데이터만으로 fit하여
    # 검증 기간의 vocabulary, IDF와 댓글 수 분포가 누출되지 않게 한다.
    train_text_features = (
        vectorizer.fit_transform(
            train_df["tfidf_text"]
        )
    )
    validation_text_features = (
        vectorizer.transform(
            validation_df["tfidf_text"]
        )
    )

    (
        train_comment_count_feature,
        comment_count_scaler,
    ) = fit_transform_comment_count_feature(
        train_df
    )
    validation_comment_count_feature = (
        transform_comment_count_feature(
            dataset=validation_df,
            scaler=comment_count_scaler,
        )
    )

    train_combined_features = (
        combine_model_features(
            tfidf_features=(
                train_text_features
            ),
            comment_count_feature=(
                train_comment_count_feature
            ),
        )
    )
    validation_combined_features = (
        combine_model_features(
            tfidf_features=(
                validation_text_features
            ),
            comment_count_feature=(
                validation_comment_count_feature
            ),
        )
    )

    return {
        "train_df": train_df,
        "validation_df": validation_df,
        "train_text_features": (
            train_text_features
        ),
        "validation_text_features": (
            validation_text_features
        ),
        "train_combined_features": (
            train_combined_features
        ),
        "validation_combined_features": (
            validation_combined_features
        ),
        "train_target": create_regression_target(
            train_df
        ),
        "validation_target": (
            create_regression_target(
                validation_df
            )
        ),
    }


def select_experiment_features(
    *,
    fold_data: dict,
    feature_mode: FeatureMode,
) -> tuple:
    """
    실험의 댓글 수 포함 여부에 맞는 훈련·검증 행렬을 선택한다.

    입력:
    - fold_data: prepare_model_fold가 만든 Fold 공통 데이터다.
    - feature_mode: text_only 또는 text_plus_comment_count다.

    출력:
    - 첫 번째 값은 모델 fit에 사용할 훈련 희소행렬이다.
    - 두 번째 값은 모델 predict에 사용할 검증 희소행렬이다.
    - 두 행렬은 동일한 특성 열 순서를 가진다.
    """
    if feature_mode == "text_only":
        return (
            fold_data["train_text_features"],
            fold_data[
                "validation_text_features"
            ],
        )

    if feature_mode == (
        "text_plus_comment_count"
    ):
        return (
            fold_data[
                "train_combined_features"
            ],
            fold_data[
                "validation_combined_features"
            ],
        )

    raise ValueError(
        "feature_mode는 text_only 또는 "
        "text_plus_comment_count여야 합니다."
    )


def calculate_coefficient_diagnostics(
    model: LinearModel,
) -> dict:
    """
    학습된 선형 모델의 전체·0 계수 개수와 희소화 비율을 계산한다.

    입력:
    - model: fit이 완료되어 coef_ 속성을 가진 Ridge 또는 ElasticNet
      모델이다.

    출력:
    - coefficient_count: 모델 입력 특성 수와 같은 전체 계수 개수다.
    - nonzero_coefficient_count: 실제 예측에 남은 0이 아닌 계수 수다.
    - zero_coefficient_count: 규제 결과 정확히 0이 된 계수 수다.
    - coefficient_sparsity_ratio: 전체 계수 중 0 계수가 차지하는
      0~1 비율이다. ElasticNet의 특성 제거 효과를 보여준다.
    """
    if not hasattr(model, "coef_"):
        raise ValueError(
            "계수 진단에는 학습된 선형 모델이 필요합니다."
        )

    coefficients = np.asarray(
        model.coef_,
        dtype=float,
    ).reshape(-1)

    if coefficients.size == 0:
        raise ValueError(
            "계수 진단에 사용할 모델 계수가 없습니다."
        )

    if not np.isfinite(coefficients).all():
        raise ValueError(
            "모델 계수에 유한하지 않은 값이 있습니다."
        )

    coefficient_count = int(
        coefficients.size
    )
    nonzero_coefficient_count = int(
        np.count_nonzero(coefficients)
    )
    zero_coefficient_count = (
        coefficient_count
        - nonzero_coefficient_count
    )

    return {
        "coefficient_count": coefficient_count,
        "nonzero_coefficient_count": (
            nonzero_coefficient_count
        ),
        "zero_coefficient_count": (
            zero_coefficient_count
        ),
        "coefficient_sparsity_ratio": (
            zero_coefficient_count
            / coefficient_count
        ),
    }


def get_model_iteration_count(
    model: LinearModel,
) -> int | None:
    """
    학습된 모델이 공개하는 최적화 반복 횟수를 정수로 변환한다.

    입력:
    - model: fit이 완료된 Ridge 또는 ElasticNet 모델이다.

    출력:
    - n_iter_가 없거나 None이면 None을 반환한다.
    - 스칼라 또는 배열이면 가장 큰 반복 횟수를 정수로 반환한다.
      이 값이 max_iter에 도달했는지 확인하여 미수렴 가능성을
      검토할 수 있다.
    """
    iteration_count = getattr(
        model,
        "n_iter_",
        None,
    )

    if iteration_count is None:
        return None

    values = np.asarray(
        iteration_count
    ).reshape(-1)

    if values.size == 0:
        return None

    return int(values.max())


def evaluate_experiment_on_fold(
    *,
    fold_data: dict,
    experiment_config: dict,
    model_variant: SupplyDirection,
    validation_start_date: date,
    validation_end_date: date,
) -> dict:
    """
    한 모델·특성 후보를 하나의 시계열 Fold에서 학습·평가한다.

    입력:
    - fold_data: prepare_model_fold가 만든 공통 행렬과 목표값이다.
    - experiment_config: 모델 종류, 특성 모드와 규제값 설정이다.
    - model_variant: positive 또는 negative 수급 방향이다.
    - validation_start_date와 validation_end_date: 결과가 어떤 미래
      구간을 평가했는지 기록할 Fold 경계다.

    출력:
    - 실험 식별자와 설정, 데이터 기간·건수, 학습·검증 성능,
      회귀계수 희소화 정도, 목표값과 예측값 분포를 하나의 dict로
      반환한다.
    - 모델 객체는 반환하거나 저장하지 않아 Fold 종료 후 폐기된다.
    """
    feature_mode: FeatureMode = (
        experiment_config["feature_mode"]
    )
    (
        train_features,
        validation_features,
    ) = select_experiment_features(
        fold_data=fold_data,
        feature_mode=feature_mode,
    )

    train_target = fold_data["train_target"]
    validation_target = fold_data[
        "validation_target"
    ]

    model = create_experiment_model(
        experiment_config
    )
    model.fit(
        train_features,
        train_target,
    )

    train_predictions = model.predict(
        train_features
    )
    validation_predictions = model.predict(
        validation_features
    )

    train_metrics = calculate_regression_metrics(
        target=train_target,
        prediction=train_predictions,
    )
    validation_metrics = (
        calculate_regression_metrics(
            target=validation_target,
            prediction=validation_predictions,
        )
    )
    coefficient_diagnostics = (
        calculate_coefficient_diagnostics(
            model
        )
    )

    train_df = fold_data["train_df"]
    validation_df = fold_data[
        "validation_df"
    ]

    result = {
        "experiment_name": experiment_config[
            "experiment_name"
        ],
        "model_type": experiment_config[
            "model_type"
        ],
        "model_class_name": type(model).__name__,
        "feature_mode": feature_mode,
        "model_variant": model_variant,
        "alpha": experiment_config["alpha"],
        "l1_ratio": experiment_config[
            "l1_ratio"
        ],
        "train_start_date": train_df[
            "model_date"
        ].min(),
        "train_end_date": train_df[
            "model_date"
        ].max(),
        "validation_start_date": (
            validation_start_date
        ),
        "validation_end_date": validation_end_date,
        "train_record_count": len(train_df),
        "validation_record_count": len(
            validation_df
        ),
        "feature_count": train_features.shape[1],
        "train_comment_count_median": float(
            train_df["comment_count"].median()
        ),
        "validation_comment_count_median": (
            float(
                validation_df[
                    "comment_count"
                ].median()
            )
        ),
        "train_target_mean": float(
            np.mean(train_target)
        ),
        "train_prediction_mean": float(
            np.mean(train_predictions)
        ),
        "validation_target_mean": float(
            np.mean(validation_target)
        ),
        "validation_prediction_mean": float(
            np.mean(validation_predictions)
        ),
        "validation_target_std": float(
            np.std(validation_target)
        ),
        "validation_prediction_std": float(
            np.std(validation_predictions)
        ),
        "validation_prediction_bias": float(
            np.mean(validation_predictions)
            - np.mean(validation_target)
        ),
        "fit_iteration_count": (
            get_model_iteration_count(model)
        ),
        "train": train_metrics,
        "validation": validation_metrics,
    }
    result.update(coefficient_diagnostics)

    return result


def run_walk_forward_evaluation() -> list[dict]:
    """
    모든 모델·특성 후보를 두 방향과 여러 시간 Fold에서 평가한다.

    입력:
    - 함수 인자는 없다. 모듈에 정의한 후보 설정과 Fold를 사용한다.

    출력:
    - 각 원소가 후보 하나의 Fold별 상세 평가 결과인 dict 목록을
      반환한다.

    부수 효과:
    - DB에서는 학습 레코드 SELECT만 수행한다.
    - 모델 파일 저장과 artifacts 테이블 INSERT는 수행하지 않는다.
    - Positive와 Negative 데이터는 각각 한 번 조회하고, Fold별
      TF-IDF 결과는 모든 후보 모델이 공유한다.
    """
    results = []
    experiment_configs = (
        create_experiment_configs()
    )

    logger.info(
        "워크포워드 실험 시작: experiment_count=%d, "
        "variant_count=%d, fold_count=%d",
        len(experiment_configs),
        len(MODEL_VARIANTS),
        len(VALIDATION_FOLDS),
    )

    for model_variant in MODEL_VARIANTS:
        records = select_model_training_records(
            tokenizer_version=TOKENIZER_VERSION,
            training_end_date=EVALUATION_END_DATE,
            supply_direction=model_variant,
        )

        if not records:
            raise ValueError(
                f"{model_variant} 방향의 평가 데이터가 없습니다."
            )

        dataset = pd.DataFrame.from_records(
            records
        )
        del records

        for fold in VALIDATION_FOLDS:
            validation_start_date = fold[
                "validation_start_date"
            ]
            validation_end_date = fold[
                "validation_end_date"
            ]
            fold_data = prepare_model_fold(
                dataset=dataset,
                validation_start_date=(
                    validation_start_date
                ),
                validation_end_date=(
                    validation_end_date
                ),
            )

            for experiment_config in (
                experiment_configs
            ):
                results.append(
                    evaluate_experiment_on_fold(
                        fold_data=fold_data,
                        experiment_config=(
                            experiment_config
                        ),
                        model_variant=model_variant,
                        validation_start_date=(
                            validation_start_date
                        ),
                        validation_end_date=(
                            validation_end_date
                        ),
                    )
                )

            logger.info(
                "워크포워드 Fold 완료: model_variant=%s, "
                "validation=%s~%s, experiment_count=%d",
                model_variant,
                validation_start_date,
                validation_end_date,
                len(experiment_configs),
            )

    return results


def aggregate_evaluation_results(
    results: list[dict],
) -> list[dict]:
    """
    Fold별 상세 결과를 모델 후보와 수급 방향별 요약으로 집계한다.

    입력:
    - results: run_walk_forward_evaluation이 반환한 Fold별 상세 결과다.

    출력:
    - 같은 experiment_name과 model_variant의 여러 Fold를 묶어 평균,
      중앙값, 최저값과 표준편차를 계산한 요약 dict 목록을 반환한다.
    - mean_train_validation_r2_gap은 학습 R²와 검증 R² 차이의
      Fold 평균으로 과적합 정도를 비교하는 보조 지표다.
    - worst_validation_start_date는 가장 낮은 검증 R²가 발생한
      Fold의 시작일이다.
    """
    grouped_results: dict[
        tuple[str, SupplyDirection],
        list[dict],
    ] = {}

    for result in results:
        key = (
            result["experiment_name"],
            result["model_variant"],
        )
        grouped_results.setdefault(
            key,
            [],
        ).append(result)

    summaries = []

    for group in grouped_results.values():
        first = group[0]
        validation_r2_values = np.asarray(
            [
                item["validation"]["r2"]
                for item in group
            ],
            dtype=float,
        )
        validation_mae_values = np.asarray(
            [
                item["validation"]["mae"]
                for item in group
            ],
            dtype=float,
        )
        validation_rmse_values = np.asarray(
            [
                item["validation"]["rmse"]
                for item in group
            ],
            dtype=float,
        )
        train_r2_values = np.asarray(
            [
                item["train"]["r2"]
                for item in group
            ],
            dtype=float,
        )
        sparsity_values = np.asarray(
            [
                item[
                    "coefficient_sparsity_ratio"
                ]
                for item in group
            ],
            dtype=float,
        )
        nonzero_coefficient_values = np.asarray(
            [
                item[
                    "nonzero_coefficient_count"
                ]
                for item in group
            ],
            dtype=float,
        )
        prediction_bias_values = np.asarray(
            [
                item[
                    "validation_prediction_bias"
                ]
                for item in group
            ],
            dtype=float,
        )

        worst_group_index = int(
            np.argmin(validation_r2_values)
        )

        summaries.append(
            {
                "experiment_name": first[
                    "experiment_name"
                ],
                "model_type": first["model_type"],
                "model_class_name": first[
                    "model_class_name"
                ],
                "feature_mode": first[
                    "feature_mode"
                ],
                "model_variant": first[
                    "model_variant"
                ],
                "alpha": first["alpha"],
                "l1_ratio": first["l1_ratio"],
                "fold_count": len(group),
                "mean_train_r2": float(
                    np.mean(train_r2_values)
                ),
                "mean_validation_mae": float(
                    np.mean(validation_mae_values)
                ),
                "mean_validation_rmse": float(
                    np.mean(validation_rmse_values)
                ),
                "mean_validation_r2": float(
                    np.mean(validation_r2_values)
                ),
                "median_validation_r2": float(
                    np.median(validation_r2_values)
                ),
                "minimum_validation_r2": float(
                    np.min(validation_r2_values)
                ),
                "validation_r2_std": float(
                    np.std(validation_r2_values)
                ),
                "mean_train_validation_r2_gap": (
                    float(
                        np.mean(
                            train_r2_values
                            - validation_r2_values
                        )
                    )
                ),
                "mean_nonzero_coefficient_count": (
                    float(
                        np.mean(
                            nonzero_coefficient_values
                        )
                    )
                ),
                "mean_coefficient_sparsity_ratio": (
                    float(
                        np.mean(sparsity_values)
                    )
                ),
                "mean_validation_prediction_bias": (
                    float(
                        np.mean(
                            prediction_bias_values
                        )
                    )
                ),
                "worst_validation_start_date": (
                    group[worst_group_index][
                        "validation_start_date"
                    ]
                ),
            }
        )

    return sorted(
        summaries,
        key=lambda item: (
            item["model_variant"],
            -item["mean_validation_r2"],
            item["experiment_name"],
        ),
    )


def create_fold_output_rows(
    results: list[dict],
) -> list[dict]:
    """
    중첩된 Fold 평가 지표를 표 출력용 1단계 dict 목록으로 변환한다.

    입력:
    - results: Fold마다 모델 설정, 기간, 성능과 계수 진단을 포함한
      상세 결과 목록이다.

    출력:
    - train과 validation 내부 dict를 열 이름이 명시된 평면 구조로
      변환한 목록을 반환한다. 원본 결과는 변경하지 않는다.
    """
    rows = []

    for result in results:
        rows.append(
            {
                "experiment_name": result[
                    "experiment_name"
                ],
                "variant": result["model_variant"],
                "model_type": result["model_type"],
                "feature_mode": result[
                    "feature_mode"
                ],
                "alpha": result["alpha"],
                "l1_ratio": result["l1_ratio"],
                "train_end": result[
                    "train_end_date"
                ],
                "validation_start": result[
                    "validation_start_date"
                ],
                "validation_end": result[
                    "validation_end_date"
                ],
                "train_count": result[
                    "train_record_count"
                ],
                "validation_count": result[
                    "validation_record_count"
                ],
                "feature_count": result[
                    "feature_count"
                ],
                "train_comment_median": result[
                    "train_comment_count_median"
                ],
                "validation_comment_median": result[
                    "validation_comment_count_median"
                ],
                "train_r2": result["train"]["r2"],
                "validation_mae": result[
                    "validation"
                ]["mae"],
                "validation_rmse": result[
                    "validation"
                ]["rmse"],
                "validation_r2": result[
                    "validation"
                ]["r2"],
                "validation_target_mean": result[
                    "validation_target_mean"
                ],
                "validation_prediction_mean": result[
                    "validation_prediction_mean"
                ],
                "validation_prediction_bias": result[
                    "validation_prediction_bias"
                ],
                "validation_target_std": result[
                    "validation_target_std"
                ],
                "validation_prediction_std": result[
                    "validation_prediction_std"
                ],
                "nonzero_coefficient_count": result[
                    "nonzero_coefficient_count"
                ],
                "coefficient_sparsity_ratio": result[
                    "coefficient_sparsity_ratio"
                ],
                "fit_iteration_count": result[
                    "fit_iteration_count"
                ],
            }
        )

    return rows


def print_tabular_results(
    *,
    title: str,
    rows: list[dict],
) -> None:
    """
    dict 목록을 발표 자료로 복사하기 쉬운 탭 구분 표로 출력한다.

    입력:
    - title: 상세 결과와 요약 결과를 구분할 표 제목이다.
    - rows: 각 dict의 key가 열 이름이고 value가 셀 값인 행 목록이다.

    출력:
    - 반환값은 없다. 제목 다음에 열 이름과 데이터를 표준 출력으로
      기록하며 실수는 소수점 여섯 자리로 통일한다.
    """
    print(title)

    if not rows:
        print("NO_RESULTS")
        return

    pd.DataFrame.from_records(rows).to_csv(
        sys.stdout,
        sep="\t",
        index=False,
        float_format="%.6f",
        lineterminator="\n",
    )


def print_evaluation_results(
    results: list[dict],
) -> None:
    """
    Fold별 상세 결과와 후보별 집계 결과를 연속해서 출력한다.

    입력:
    - results: run_walk_forward_evaluation의 Fold별 상세 결과다.

    출력:
    - 반환값은 없다. FOLD_RESULTS 표 다음에 SUMMARY_RESULTS 표를
      출력하여 원본 근거와 최종 비교를 한 실행에서 함께 남긴다.
    """
    print_tabular_results(
        title="FOLD_RESULTS",
        rows=create_fold_output_rows(results),
    )
    print_tabular_results(
        title="SUMMARY_RESULTS",
        rows=aggregate_evaluation_results(results),
    )


def main() -> None:
    """워크포워드 실험을 실행하고 상세·요약 표를 출력한다."""
    results = run_walk_forward_evaluation()
    print_evaluation_results(results)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        ),
    )
    main()
