import logging

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from scipy.sparse import csr_matrix

from pilos.analysis.modeling.model_features import (
    combine_model_features,
    fit_transform_comment_count_feature,
    transform_comment_count_feature,
)
from pilos.analysis.modeling.model_inference import (
    analyze_text_contributions,
)
from pilos.analysis.modeling.model_train import (
    calculate_regression_metrics,
    create_regression_target,
)
from pilos.analysis.modeling.model_validation import (
    create_month_stratified_date_groups,
    split_dataset_by_date_groups,
)
from pilos.analysis.tokenizer_settings import (
    TOKENIZER_VERSION,
)
from pilos.analysis.vectorizer import (
    create_tfidf_vectorizer,
)
from pilos.jobs.evaluate_model_walk_forward import (
    FeatureMode,
    calculate_coefficient_diagnostics,
    create_experiment_model,
    get_model_iteration_count,
    select_experiment_features,
)
from pilos.jobs.train_model import (
    LOWERCASE,
    MAX_DF,
    MAX_FEATURES,
    MIN_DF,
    NGRAM_RANGE,
    SUBLINEAR_TF,
)
from pilos.storage.csv import (
    save_csv_records,
)
from pilos.storage.model_training_db import (
    SupplyDirection,
    select_model_training_records,
)

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
EVALUATION_END_DATE = date(2026, 7, 24)

# 월별 고유 날짜의 약 20%를 검증에 사용한다. 같은 날짜의 모든 종목은
# 동일한 분할에 들어가며 Positive와 Negative도 같은 날짜 분할을 쓴다.
VALIDATION_RATIO = 0.2
RANDOM_SEEDS = (
    42,
    43,
    44,
    45,
    46,
)
TOP_N_KEYWORDS = 10

OUTPUT_DIR = (
    BASE_DIR
    / "data"
    / "review"
    / "model_grouped_random"
)
FOLD_RESULTS_OUTPUT_PATH = (
    OUTPUT_DIR / "fold_results.csv"
)
SUMMARY_RESULTS_OUTPUT_PATH = (
    OUTPUT_DIR / "summary_results.csv"
)
KEYWORD_RESULTS_OUTPUT_PATH = (
    OUTPUT_DIR / "keyword_results.csv"
)

# 워크포워드 40개 후보에서 성능과 안정성의 의미가 있었던 조합만
# 방향별로 세 개씩 재검증한다. 모델 계열, 규제와 댓글 수의 효과를
# 최소한의 학습 횟수로 비교하기 위한 발표용 shortlist다.
EXPERIMENT_CONFIGS_BY_VARIANT: dict[
    SupplyDirection,
    tuple[dict, ...],
] = {
    "positive": (
        {
            "experiment_name": "ridge__text_only__alpha_1",
            "model_type": "ridge",
            "feature_mode": "text_only",
            "alpha": 1.0,
            "l1_ratio": None,
        },
        {
            "experiment_name": "ridge__text_only__alpha_10",
            "model_type": "ridge",
            "feature_mode": "text_only",
            "alpha": 10.0,
            "l1_ratio": None,
        },
        {
            "experiment_name": (
                "elastic_net__text_only__alpha_0.001__l1_0.1"
            ),
            "model_type": "elastic_net",
            "feature_mode": "text_only",
            "alpha": 0.001,
            "l1_ratio": 0.1,
        },
    ),
    "negative": (
        {
            "experiment_name": "ridge__text_only__alpha_1",
            "model_type": "ridge",
            "feature_mode": "text_only",
            "alpha": 1.0,
            "l1_ratio": None,
        },
        {
            "experiment_name": (
                "ridge__text_plus_comment_count__alpha_1"
            ),
            "model_type": "ridge",
            "feature_mode": "text_plus_comment_count",
            "alpha": 1.0,
            "l1_ratio": None,
        },
        {
            "experiment_name": (
                "elastic_net__text_plus_comment_count__"
                "alpha_0.0001__l1_0.9"
            ),
            "model_type": "elastic_net",
            "feature_mode": "text_plus_comment_count",
            "alpha": 0.0001,
            "l1_ratio": 0.9,
        },
    ),
}

# CLI:
# uv run python -m pilos.jobs.evaluate_model_grouped_random


def prepare_grouped_random_fold(
    *,
    dataset: pd.DataFrame,
    train_dates: frozenset[date],
    validation_dates: frozenset[date],
) -> dict:
    """
    한 방향·한 시드의 공통 훈련·검증 특성과 목표값을 준비한다.

    입력:
    - dataset: 한 수급 방향의 전체 일별 모델 학습 레코드다.
    - train_dates: 월별 층화 랜덤 분할에서 훈련으로 선택된 날짜다.
    - validation_dates: 같은 분할에서 검증으로 선택된 날짜다.

    출력:
    - 훈련·검증 원본 DataFrame, TF-IDF 행렬, 댓글 수를 결합한 행렬,
      목표값, 학습된 Vectorizer를 포함한 dict를 반환한다.

    Vectorizer와 댓글 수 Scaler는 훈련 행으로만 fit한다. 같은 방향과
    시드의 세 모델 후보는 반환된 행렬을 공유하여 입력 차이 없이 모델
    종류와 규제·댓글 수 특성의 효과만 비교한다.
    """
    train_df, validation_df = (
        split_dataset_by_date_groups(
            dataset=dataset,
            train_dates=train_dates,
            validation_dates=validation_dates,
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
    train_text_features = vectorizer.fit_transform(
        train_df["tfidf_text"]
    )
    validation_text_features = vectorizer.transform(
        validation_df["tfidf_text"]
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

    return {
        "train_df": train_df,
        "validation_df": validation_df,
        "train_text_features": train_text_features,
        "validation_text_features": validation_text_features,
        "train_combined_features": combine_model_features(
            tfidf_features=train_text_features,
            comment_count_feature=train_comment_count_feature,
        ),
        "validation_combined_features": combine_model_features(
            tfidf_features=validation_text_features,
            comment_count_feature=(
                validation_comment_count_feature
            ),
        ),
        "train_target": create_regression_target(
            train_df
        ),
        "validation_target": create_regression_target(
            validation_df
        ),
        "vectorizer": vectorizer,
    }


def _extract_scalar_intercept(model) -> float:
    """학습된 단일 출력 선형 모델의 절편을 실수 하나로 반환한다."""
    intercept_values = np.asarray(
        model.intercept_,
        dtype=float,
    ).reshape(-1)

    if intercept_values.size != 1:
        raise ValueError(
            "단일 수급지수 모델의 절편은 하나여야 합니다."
        )

    intercept = float(intercept_values[0])

    if not np.isfinite(intercept):
        raise ValueError(
            "모델 절편이 유한하지 않습니다."
        )

    return intercept


def decode_validation_keywords(
    *,
    model,
    fold_data: dict,
    experiment_config: dict,
    model_variant: SupplyDirection,
    random_seed: int,
) -> tuple[list[dict], float]:
    """
    평균 검증 문서에서 양수·음수 기여도 상위 키워드를 디코딩한다.

    입력:
    - model: 현재 Fold에서 학습된 Ridge 또는 ElasticNet 모델이다.
    - fold_data: 검증 TF-IDF 행렬과 Vectorizer를 포함한 공통 데이터다.
    - experiment_config: 결과 식별용 모델·특성·규제 설정이다.
    - model_variant: positive 또는 negative 수급 방향이다.
    - random_seed: 현재 날짜 분할을 만든 난수 시드다.

    출력:
    - 첫 번째 값은 기존 analyze_text_contributions 함수가 계산한
      양수 10개와 음수 10개의 기여도 행 목록이다.
    - 두 번째 값은 평균 검증 문서의 텍스트 기여도 합이다.

    검증 TF-IDF의 열별 평균은 해당 Fold에서 관측된 대표 문서를
    의미한다. 따라서 계수 절댓값만 정렬하지 않고 실제 검증 문서의
    출현 강도와 모델 계수를 함께 반영한다.
    """
    validation_text_features = fold_data[
        "validation_text_features"
    ]
    mean_validation_tfidf = csr_matrix(
        np.asarray(
            validation_text_features.mean(axis=0)
        )
    )
    feature_names = fold_data[
        "vectorizer"
    ].get_feature_names_out()
    text_feature_count = len(feature_names)
    model_coefficients = np.asarray(
        model.coef_,
        dtype=float,
    ).reshape(-1)
    text_coefficients = model_coefficients[
        :text_feature_count
    ]

    decoded = analyze_text_contributions(
        tfidf_row=mean_validation_tfidf,
        feature_names=feature_names,
        text_coefficients=text_coefficients,
        top_n=TOP_N_KEYWORDS,
    )
    keyword_rows = []

    keyword_groups = (
        (
            "positive_contribution",
            decoded["positive_keywords"],
        ),
        (
            "negative_contribution",
            decoded["negative_keywords"],
        ),
    )

    for keyword_direction, keywords in keyword_groups:
        for keyword in keywords:
            keyword_rows.append(
                {
                    "experiment_name": experiment_config[
                        "experiment_name"
                    ],
                    "variant": model_variant,
                    "random_seed": random_seed,
                    "keyword_direction": keyword_direction,
                    "rank": keyword["rank"],
                    "word": keyword["word"],
                    "mean_validation_tfidf": keyword["tfidf"],
                    "coefficient": keyword["coefficient"],
                    "contribution": keyword["contribution"],
                }
            )

    return keyword_rows, decoded["text_score"]


def evaluate_experiment_on_random_fold(
    *,
    fold_data: dict,
    experiment_config: dict,
    model_variant: SupplyDirection,
    random_seed: int,
) -> tuple[dict, list[dict]]:
    """
    한 모델 후보를 한 날짜 그룹 랜덤 Fold에서 학습·평가한다.

    입력:
    - fold_data: 한 방향과 시드에서 공통으로 사용할 특성과 목표값이다.
    - experiment_config: 모델 종류, 특성 모드와 규제 설정이다.
    - model_variant: positive 또는 negative 수급 방향이다.
    - random_seed: 현재 월별 날짜 그룹 분할의 식별자다.

    출력:
    - 첫 번째 dict는 행 수, 날짜 수, 성능, 편향과 계수 진단이다.
    - 두 번째 목록은 평균 검증 문서의 상위 키워드 기여도다.
    """
    feature_mode: FeatureMode = experiment_config[
        "feature_mode"
    ]
    train_features, validation_features = (
        select_experiment_features(
            fold_data=fold_data,
            feature_mode=feature_mode,
        )
    )
    model = create_experiment_model(
        experiment_config
    )
    train_target = fold_data["train_target"]
    validation_target = fold_data[
        "validation_target"
    ]
    model.fit(train_features, train_target)

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
    validation_metrics = calculate_regression_metrics(
        target=validation_target,
        prediction=validation_predictions,
    )
    coefficient_diagnostics = (
        calculate_coefficient_diagnostics(model)
    )

    text_feature_count = fold_data[
        "train_text_features"
    ].shape[1]
    model_coefficients = np.asarray(
        model.coef_,
        dtype=float,
    ).reshape(-1)
    comment_count_coefficient = None

    if feature_mode == "text_plus_comment_count":
        comment_count_coefficient = float(
            model_coefficients[text_feature_count]
        )

    keyword_rows, mean_validation_text_score = (
        decode_validation_keywords(
            model=model,
            fold_data=fold_data,
            experiment_config=experiment_config,
            model_variant=model_variant,
            random_seed=random_seed,
        )
    )
    train_df = fold_data["train_df"]
    validation_df = fold_data["validation_df"]
    train_date_values = sorted(
        train_df["model_date"].unique()
    )
    validation_date_values = sorted(
        validation_df["model_date"].unique()
    )

    result = {
        "experiment_name": experiment_config[
            "experiment_name"
        ],
        "variant": model_variant,
        "model_type": experiment_config["model_type"],
        "model_class_name": type(model).__name__,
        "feature_mode": feature_mode,
        "alpha": experiment_config["alpha"],
        "l1_ratio": experiment_config["l1_ratio"],
        "random_seed": random_seed,
        "validation_ratio": VALIDATION_RATIO,
        "train_start_date": min(train_date_values),
        "train_end_date": max(train_date_values),
        "validation_start_date": min(validation_date_values),
        "validation_end_date": max(validation_date_values),
        "train_date_count": len(train_date_values),
        "validation_date_count": len(validation_date_values),
        "train_record_count": len(train_df),
        "validation_record_count": len(validation_df),
        "validation_dates": ";".join(
            value.isoformat()
            for value in validation_date_values
        ),
        "text_feature_count": text_feature_count,
        "feature_count": train_features.shape[1],
        "train_comment_count_median": float(
            train_df["comment_count"].median()
        ),
        "validation_comment_count_median": float(
            validation_df["comment_count"].median()
        ),
        "train_target_mean": float(
            np.mean(train_target)
        ),
        "validation_target_mean": float(
            np.mean(validation_target)
        ),
        "validation_prediction_mean": float(
            np.mean(validation_predictions)
        ),
        "validation_prediction_bias": float(
            np.mean(validation_predictions)
            - np.mean(validation_target)
        ),
        "validation_target_std": float(
            np.std(validation_target)
        ),
        "validation_prediction_std": float(
            np.std(validation_predictions)
        ),
        "train_mae": train_metrics["mae"],
        "train_rmse": train_metrics["rmse"],
        "train_r2": train_metrics["r2"],
        "validation_mae": validation_metrics["mae"],
        "validation_rmse": validation_metrics["rmse"],
        "validation_r2": validation_metrics["r2"],
        "train_validation_r2_gap": (
            train_metrics["r2"]
            - validation_metrics["r2"]
        ),
        "coefficient_count": coefficient_diagnostics[
            "coefficient_count"
        ],
        "nonzero_coefficient_count": coefficient_diagnostics[
            "nonzero_coefficient_count"
        ],
        "zero_coefficient_count": coefficient_diagnostics[
            "zero_coefficient_count"
        ],
        "coefficient_sparsity_ratio": coefficient_diagnostics[
            "coefficient_sparsity_ratio"
        ],
        "comment_count_coefficient": comment_count_coefficient,
        "intercept": _extract_scalar_intercept(model),
        "mean_validation_text_score": mean_validation_text_score,
        "fit_iteration_count": get_model_iteration_count(model),
    }

    return result, keyword_rows


def aggregate_random_results(
    fold_results: list[dict],
) -> list[dict]:
    """
    시드별 상세 결과를 모델 후보와 수급 방향별 요약으로 집계한다.

    입력:
    - fold_results: 각 시드에서 한 후보를 평가한 평면 dict 목록이다.

    출력:
    - 후보별 검증 R² 평균·중앙값·최저값·표준편차, MAE, RMSE,
      학습-검증 격차, 편향과 계수 희소성 평균을 포함한 목록이다.
    """
    grouped_results: dict[tuple[str, str], list[dict]] = {}

    for result in fold_results:
        key = (
            result["experiment_name"],
            result["variant"],
        )
        grouped_results.setdefault(key, []).append(result)

    summaries = []

    for group in grouped_results.values():
        first = group[0]

        def values(field_name: str) -> np.ndarray:
            """현재 후보의 숫자 필드를 실수 배열로 변환한다."""
            return np.asarray(
                [item[field_name] for item in group],
                dtype=float,
            )

        validation_r2_values = values("validation_r2")
        comment_count_values = [
            item["comment_count_coefficient"]
            for item in group
            if item["comment_count_coefficient"] is not None
        ]

        summaries.append(
            {
                "experiment_name": first["experiment_name"],
                "variant": first["variant"],
                "model_type": first["model_type"],
                "model_class_name": first["model_class_name"],
                "feature_mode": first["feature_mode"],
                "alpha": first["alpha"],
                "l1_ratio": first["l1_ratio"],
                "seed_count": len(group),
                "mean_train_r2": float(
                    np.mean(values("train_r2"))
                ),
                "mean_validation_mae": float(
                    np.mean(values("validation_mae"))
                ),
                "mean_validation_rmse": float(
                    np.mean(values("validation_rmse"))
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
                "maximum_validation_r2": float(
                    np.max(validation_r2_values)
                ),
                "validation_r2_std": float(
                    np.std(validation_r2_values)
                ),
                "mean_train_validation_r2_gap": float(
                    np.mean(
                        values("train_validation_r2_gap")
                    )
                ),
                "mean_validation_prediction_bias": float(
                    np.mean(
                        values("validation_prediction_bias")
                    )
                ),
                "mean_nonzero_coefficient_count": float(
                    np.mean(
                        values("nonzero_coefficient_count")
                    )
                ),
                "mean_coefficient_sparsity_ratio": float(
                    np.mean(
                        values("coefficient_sparsity_ratio")
                    )
                ),
                "mean_comment_count_coefficient": (
                    float(np.mean(comment_count_values))
                    if comment_count_values
                    else None
                ),
            }
        )

    return sorted(
        summaries,
        key=lambda item: (
            item["variant"],
            -item["mean_validation_r2"],
            item["experiment_name"],
        ),
    )


def run_grouped_random_evaluation(
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    두 수급 방향의 shortlist를 다섯 날짜 그룹 분할에서 평가한다.

    입력:
    - 함수 인자는 없다. 모듈의 종료일, 시드와 후보 설정을 사용한다.

    출력:
    - 시드별 상세 결과 30행, 후보별 요약 결과 6행, 키워드 기여도
      결과 목록을 차례로 반환한다.

    부수 효과:
    - DB에서는 모델 학습 레코드 SELECT만 수행한다.
    - 모델 아티팩트 저장과 DB INSERT는 수행하지 않는다.
    """
    datasets: dict[SupplyDirection, pd.DataFrame] = {}

    for model_variant in EXPERIMENT_CONFIGS_BY_VARIANT:
        records = select_model_training_records(
            tokenizer_version=TOKENIZER_VERSION,
            training_end_date=EVALUATION_END_DATE,
            supply_direction=model_variant,
        )

        if not records:
            raise ValueError(
                f"{model_variant} 방향의 평가 데이터가 없습니다."
            )

        datasets[model_variant] = pd.DataFrame.from_records(
            records
        )

    all_model_dates = []

    for dataset in datasets.values():
        all_model_dates.extend(
            dataset["model_date"].tolist()
        )

    fold_results = []
    keyword_results = []

    for random_seed in RANDOM_SEEDS:
        train_dates, validation_dates = (
            create_month_stratified_date_groups(
                model_dates=all_model_dates,
                validation_ratio=VALIDATION_RATIO,
                random_seed=random_seed,
            )
        )

        for model_variant, dataset in datasets.items():
            fold_data = prepare_grouped_random_fold(
                dataset=dataset,
                train_dates=train_dates,
                validation_dates=validation_dates,
            )

            for experiment_config in (
                EXPERIMENT_CONFIGS_BY_VARIANT[model_variant]
            ):
                result, decoded_keywords = (
                    evaluate_experiment_on_random_fold(
                        fold_data=fold_data,
                        experiment_config=experiment_config,
                        model_variant=model_variant,
                        random_seed=random_seed,
                    )
                )
                fold_results.append(result)
                keyword_results.extend(decoded_keywords)

            logger.info(
                "날짜 그룹 랜덤 Fold 완료: variant=%s, seed=%d, "
                "train_dates=%d, validation_dates=%d",
                model_variant,
                random_seed,
                fold_data["train_df"]["model_date"].nunique(),
                fold_data["validation_df"]["model_date"].nunique(),
            )

    summary_results = aggregate_random_results(
        fold_results
    )

    return (
        fold_results,
        summary_results,
        keyword_results,
    )


def save_grouped_random_results(
    *,
    fold_results: list[dict],
    summary_results: list[dict],
    keyword_results: list[dict],
) -> dict[str, int]:
    """
    랜덤 평가의 상세·요약·키워드 결과를 세 CSV로 저장한다.

    입력:
    - fold_results: 시드별 상세 평가 행 목록이다.
    - summary_results: 모델 후보별 집계 행 목록이다.
    - keyword_results: 평균 검증 문서의 키워드 기여도 행 목록이다.

    출력:
    - 각 CSV 이름과 저장된 데이터 행 수를 연결한 dict를 반환한다.
    """
    return {
        "fold_results.csv": save_csv_records(
            records=fold_results,
            output_path=FOLD_RESULTS_OUTPUT_PATH,
        ),
        "summary_results.csv": save_csv_records(
            records=summary_results,
            output_path=SUMMARY_RESULTS_OUTPUT_PATH,
        ),
        "keyword_results.csv": save_csv_records(
            records=keyword_results,
            output_path=KEYWORD_RESULTS_OUTPUT_PATH,
        ),
    }


def main() -> None:
    """랜덤 평가를 실행하고 세 CSV의 경로와 행 수를 로그로 남긴다."""
    (
        fold_results,
        summary_results,
        keyword_results,
    ) = run_grouped_random_evaluation()
    saved_row_counts = save_grouped_random_results(
        fold_results=fold_results,
        summary_results=summary_results,
        keyword_results=keyword_results,
    )

    logger.info(
        "날짜 그룹 랜덤 평가 완료: output_dir=%s, rows=%s",
        OUTPUT_DIR,
        saved_row_counts,
    )


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
