import logging

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from pilos.analysis.tokenizer_settings import (
    TOKENIZER_VERSION,
)
from pilos.analysis.modeling.model_train import (
    calculate_regression_metrics,
    create_regression_target,
)
from pilos.analysis.modeling.model_validation import (
    create_month_stratified_date_groups,
    split_dataset_by_date_groups,
)
from pilos.analysis.modeling.ridge_model import (
    create_ridge_model,
)
from pilos.analysis.vectorizer import (
    create_tfidf_vectorizer,
)
from pilos.storage.model_training_db import (
    SupplyDirection,
    insert_model_artifact,
    select_model_artifact,
    select_model_training_records,
)
from pilos.storage.model_artifacts import (
    MODEL_ARTIFACT_SCHEMA_VERSION,
    load_model_artifacts,
    save_model_artifacts,
)
from pilos.model_config import (
    SERVICE_MODEL_ARTIFACT_SCHEMA_VERSION,
    SERVICE_MODEL_NAME,
    SERVICE_MODEL_VARIANTS,
)

logger = logging.getLogger(__name__)

RIDGE_ALPHA = 1.0                   # Ridge 규제 강도입니다. 가장 중요하게 조정할 값입니다. 값이 클수록 단어별 계수를 강하게 축소하여 과적합을 줄입니다.
RIDGE_FIT_INTERCEPT = True          # 절편을 학습할지 결정합니다. 목표값 평균이 정확히 0이라고 보장할 수 없으므로 기본적으로 True가 적절합니다.
RIDGE_SOLVER = "lsqr"               # 계수를 계산하는 방법입니다. "lsqr"는 현재처럼 특성 수가 많고 입력이 희소행렬인 경우에 사용할 수 있습니다.
RIDGE_TOL = 1e-4                    # 계산을 어느 정도 정밀도에서 종료할지 결정합니다. 작을수록 정밀하지만 시간이 더 걸릴 수 있습니다.
RIDGE_MAX_ITER = None               # 반복 계산의 최대 횟수입니다. None이면 solver의 기본값을 사용합니다.
RIDGE_POSITIVE = False              # 모든 계수를 양수로 제한할지 결정합니다. 부정적인 단어 효과도 표현해야 하므로 현재 모델에서는 False가 맞습니다.

NGRAM_RANGE = (1, 1)
MIN_DF = 5
MAX_DF = 0.95
MAX_FEATURES = None
SUBLINEAR_TF = True
LOWERCASE = True

BASE_DIR = Path(__file__).resolve().parents[2]
TRAINING_TARGET_MODEL_VERSION = 4

ARTIFACT_TYPE = "ridge_text_grouped_random_bundle"
ARTIFACT_SCHEMA_VERSION = SERVICE_MODEL_ARTIFACT_SCHEMA_VERSION
MODEL_NAME = SERVICE_MODEL_NAME
FEATURE_MODE = "text_only"
SCALER_NAME = "not_used"

POSITIVE_MODEL_OUTPUT_PATH = (
    BASE_DIR
    / "artifacts"
    / f"{MODEL_NAME}_positive_text_only_v{TRAINING_TARGET_MODEL_VERSION}.pkl"
)

NEGATIVE_MODEL_OUTPUT_PATH = (
    BASE_DIR
    / "artifacts"
    / f"{MODEL_NAME}_negative_text_only_v{TRAINING_TARGET_MODEL_VERSION}.pkl"
)

TRAINING_END_DATE = date(2026, 7, 24)
VALIDATION_RATIO = 0.2
RANDOM_SEEDS = (42, 43, 44, 45, 46)

MODEL_TRAINING_CONFIGS = tuple(
    {
        "model_variant": model_variant,
        "model_version": TRAINING_TARGET_MODEL_VERSION,
        "model_output_path": (
            POSITIVE_MODEL_OUTPUT_PATH if model_variant == "positive" else NEGATIVE_MODEL_OUTPUT_PATH
        ),
    }
    for model_variant in SERVICE_MODEL_VARIANTS
)

# CLI :
# uv run python -m pilos.jobs.train_model


def _fit_selected_text_only_model(
    dataset: pd.DataFrame,
) -> dict:
    """
    전달받은 Dataset 전체로 선정된 text-only Ridge를 학습한다.

    입력:
    - dataset: tfidf_text와 supply_demand_index를 포함하는 비어 있지
      않은 한 수급 방향의 DataFrame이다.

    출력:
    - 훈련된 vectorizer와 ridge_model, TF-IDF 희소행렬, 목표값,
      예측값 및 Dataset 자체에 대한 회귀 지표를 포함한 dict다.

    이 함수는 평가용 훈련 구간과 최종 서비스용 전체 Dataset에 동일한
    모델 설정을 적용하기 위해 사용한다. 댓글 수는 입력 특성에 포함하지
    않는다.
    """
    if dataset.empty:
        raise ValueError(
            "text-only Ridge를 학습할 Dataset이 비어 있습니다."
        )

    vectorizer = create_tfidf_vectorizer(
        lowercase=LOWERCASE,
        ngram_range=NGRAM_RANGE,
        min_df=MIN_DF,
        max_df=MAX_DF,
        max_features=MAX_FEATURES,
        sublinear_tf=SUBLINEAR_TF,
    )
    features = vectorizer.fit_transform(
        dataset["tfidf_text"]
    )
    target = create_regression_target(dataset)
    ridge_model = create_ridge_model(
        alpha=RIDGE_ALPHA,
        fit_intercept=RIDGE_FIT_INTERCEPT,
        solver=RIDGE_SOLVER,
        tol=RIDGE_TOL,
        max_iter=RIDGE_MAX_ITER,
        positive=RIDGE_POSITIVE,
    )
    ridge_model.fit(features, target)
    predictions = ridge_model.predict(features)
    metrics = calculate_regression_metrics(
        target=target,
        prediction=predictions,
    )

    return {
        "vectorizer": vectorizer,
        "ridge_model": ridge_model,
        "features": features,
        "target": target,
        "predictions": predictions,
        "metrics": metrics,
    }


def _load_training_datasets() -> dict[SupplyDirection, pd.DataFrame]:
    """두 수급 방향의 7월 24일까지 학습 데이터를 DB에서 조회한다."""
    datasets = {}

    for config in MODEL_TRAINING_CONFIGS:
        model_variant = config["model_variant"]
        training_records = select_model_training_records(
            tokenizer_version=TOKENIZER_VERSION,
            training_end_date=TRAINING_END_DATE,
            supply_direction=model_variant,
        )

        if not training_records:
            raise ValueError(
                f"{model_variant} 방향의 학습 데이터가 없습니다."
            )

        dataset = pd.DataFrame.from_records(training_records)
        datasets[model_variant] = dataset
        logger.info(
            "학습 데이터 조회 완료: model_variant=%s, count=%d, "
            "date_range=%s~%s",
            model_variant,
            len(dataset),
            dataset["model_date"].min(),
            dataset["model_date"].max(),
        )

    return datasets


def _create_shared_validation_splits(
    datasets: dict[SupplyDirection, pd.DataFrame],
) -> dict[int, tuple[frozenset[date], frozenset[date]]]:
    """
    양·음수 모델이 공유할 월별 층화 날짜 분할을 시드별로 생성한다.

    두 방향의 전체 관측 날짜를 합친 뒤 날짜 단위로 분리하므로 같은 날이
    한 방향에서는 훈련, 다른 방향에서는 검증에 들어가지 않는다.
    """
    all_model_dates = []

    for dataset in datasets.values():
        all_model_dates.extend(dataset["model_date"].tolist())

    return {
        random_seed: create_month_stratified_date_groups(
            model_dates=all_model_dates,
            validation_ratio=VALIDATION_RATIO,
            random_seed=random_seed,
        )
        for random_seed in RANDOM_SEEDS
    }


def _evaluate_selected_model_grouped_random(
    *,
    dataset: pd.DataFrame,
    model_variant: SupplyDirection,
    shared_date_splits: dict[
        int,
        tuple[frozenset[date], frozenset[date]],
    ],
) -> dict:
    """
    선정 모델을 다섯 개의 월별 층화 날짜 분할로 반복 검증한다.

    입력 Dataset은 시드마다 임시 훈련·검증 데이터로 분리되며 Vectorizer와
    Ridge도 매번 새로 학습한다. 출력 지표는 임시 모델들의 계수 평균이
    아니라 각 검증 지표의 산술평균이다.
    """
    fold_results = []

    for random_seed, date_groups in shared_date_splits.items():
        train_dates, validation_dates = date_groups
        evaluation_train_df, validation_df = split_dataset_by_date_groups(
            dataset=dataset,
            train_dates=train_dates,
            validation_dates=validation_dates,
        )
        evaluation_result = _fit_selected_text_only_model(
            evaluation_train_df
        )
        validation_features = evaluation_result["vectorizer"].transform(
            validation_df["tfidf_text"]
        )
        validation_target = create_regression_target(validation_df)
        validation_predictions = evaluation_result["ridge_model"].predict(
            validation_features
        )
        validation_metrics = calculate_regression_metrics(
            target=validation_target,
            prediction=validation_predictions,
        )
        fold_results.append(
            {
                "random_seed": random_seed,
                "train_record_count": len(evaluation_train_df),
                "validation_record_count": len(validation_df),
                "validation": validation_metrics,
            }
        )
        logger.info(
            "랜덤 날짜 검증 완료: model_variant=%s, seed=%d, "
            "train_count=%d, validation_count=%d, "
            "validation_mae=%.6f, validation_rmse=%.6f, "
            "validation_r2=%.6f",
            model_variant,
            random_seed,
            len(evaluation_train_df),
            len(validation_df),
            validation_metrics["mae"],
            validation_metrics["rmse"],
            validation_metrics["r2"],
        )

    mean_metrics = {
        metric_name: float(np.mean([
            fold["validation"][metric_name]
            for fold in fold_results
        ]))
        for metric_name in ("mae", "rmse", "r2")
    }
    mean_validation_record_count = float(np.mean([
        fold["validation_record_count"]
        for fold in fold_results
    ]))

    logger.info(
        "반복 랜덤 검증 평균: model_variant=%s, repeat_count=%d, "
        "validation_count_mean=%.1f, validation_mae=%.6f, "
        "validation_rmse=%.6f, validation_r2=%.6f",
        model_variant,
        len(fold_results),
        mean_validation_record_count,
        mean_metrics["mae"],
        mean_metrics["rmse"],
        mean_metrics["r2"],
    )

    return {
        "folds": fold_results,
        "validation": mean_metrics,
        "mean_validation_record_count": mean_validation_record_count,
        "validation_record_count": int(round(mean_validation_record_count)),
    }


def run_train_model(
    *,
    dataset: pd.DataFrame,
    shared_date_splits: dict[
        int,
        tuple[frozenset[date], frozenset[date]],
    ],
    model_variant: SupplyDirection,
    model_version: int,
    model_output_path: Path,
) -> dict:
    """
    한 수급 방향의 선정 Ridge를 평가한 뒤 전체 데이터로 최종 학습한다.

    입력:
    - dataset: DB에서 조회한 한 수급 방향의 전체 학습 DataFrame이다.
    - shared_date_splits: 양·음수 모델이 공유하는 시드별 날짜 집합이다.
    - model_variant: positive 또는 negative 수급 방향이다.
    - model_version: 저장·조회에 사용할 서비스 모델 버전이다.
    - model_output_path: 최종 스키마 v2 bundle을 저장할 로컬 경로다.

    출력:
    - DB artifact_id, 모델 방향·버전·저장 경로와 전체 학습 및 반복 랜덤
      검증 지표를 포함한 dict를 반환한다.

    실행 순서:
    1. 월별 날짜 분포를 유지한 다섯 개의 80:20 분할로 검증 지표의
       평균을 계산한다.
    2. 검증과 분리된 새 Vectorizer와 Ridge를 Dataset 전체로 다시
       학습하여 실제 서비스 bundle로 저장한다.
    3. 저장 파일을 다시 로드해 예측값을 재현한 뒤 DB에 정보를 등록한다.

    같은 버전의 DB 행이나 로컬 파일이 이미 있으면 덮어쓰지 않는다.
    """
    existing_artifact = select_model_artifact(
        model_name=MODEL_NAME,
        model_variant=model_variant,
        model_version=model_version,
        artifact_schema_version=(
            ARTIFACT_SCHEMA_VERSION
        ),
    )

    if existing_artifact is not None:
        raise ValueError(
            "같은 모델명·방향·버전의 아티팩트가 이미 존재합니다: "
            f"artifact_id={existing_artifact['artifact_id']}"
        )

    if model_output_path.exists():
        raise FileExistsError(
            "모델 파일을 덮어쓰지 않습니다: "
            f"{model_output_path}"
        )

    if dataset.empty:
        raise ValueError(
            f"{model_variant} 방향의 학습 데이터가 없습니다."
        )

    dataset_start_date = dataset["model_date"].min()
    dataset_last_date = dataset["model_date"].max()

    logger.info(
        "모델 학습 시작: model_variant=%s, model_version=%d, "
        "record_count=%d, date_range=%s~%s",
        model_variant,
        model_version,
        len(dataset),
        dataset_start_date,
        dataset_last_date,
    )

    validation_summary = _evaluate_selected_model_grouped_random(
        dataset=dataset,
        model_variant=model_variant,
        shared_date_splits=shared_date_splits,
    )

    # 다섯 임시 모델의 계수를 합치지 않는다. 검증이 끝나면 전체 Dataset으로
    # vocabulary, IDF와 Ridge 계수를 처음부터 다시 학습한다.
    final_result = _fit_selected_text_only_model(
        dataset
    )
    final_train_metrics = final_result["metrics"]

    save_model_artifacts(
        vectorizer=final_result["vectorizer"],
        ridge_model=final_result["ridge_model"],
        model_name=MODEL_NAME,
        model_variant=model_variant,
        model_version=model_version,
        tokenizer_version=TOKENIZER_VERSION,
        dataset_start_date=dataset_start_date,
        dataset_end_date=dataset_last_date,
        output_path=model_output_path,
    )

    # 저장 직후 같은 공개 로더로 다시 읽어 실제 추론 경로에서 모델과
    # 메타데이터가 복원되는지 확인한다.
    loaded_artifacts = load_model_artifacts(
        model_output_path
    )
    loaded_features = loaded_artifacts[
        "vectorizer"
    ].transform(dataset["tfidf_text"])
    loaded_predictions = loaded_artifacts[
        "ridge_model"
    ].predict(loaded_features)

    if not np.allclose(
        final_result["predictions"],
        loaded_predictions,
    ):
        raise RuntimeError(
            "저장 전후의 전체 Dataset 예측값이 다릅니다."
        )

    logger.info(
        "전체 Dataset 모델 저장·재로드 완료: model_variant=%s, "
        "record_count=%d, train_r2=%.6f, path=%s",
        model_variant,
        len(dataset),
        final_train_metrics["r2"],
        model_output_path,
    )

    # 집과 학원에서 저장소의 절대 위치가 달라도 같은 값을
    # 사용할 수 있도록 DB에는 저장소 기준 상대 경로를 기록한다
    saved_path = (
        model_output_path
        .relative_to(BASE_DIR)
        .as_posix()
    )

    artifact_data = {
        "artifact_type": ARTIFACT_TYPE,
        "saved_path": saved_path,
        "artifact_schema_version": (
            ARTIFACT_SCHEMA_VERSION
        ),
        "model_name": MODEL_NAME,
        "model_variant": model_variant,
        "model_version": model_version,
        "vectorizer_name": type(
            final_result["vectorizer"]
        ).__name__,
        "scaler_name": SCALER_NAME,
        "tokenizer_version": TOKENIZER_VERSION,
        "dataset_start_date": dataset_start_date,
        "dataset_end_date": dataset_last_date,
        # 랜덤 검증에 참여할 수 있었던 전체 Dataset 기간의 시작일이다.
        "validation_start_date": dataset_start_date,
        # 저장된 서비스 모델은 검증 행을 포함한 전체 Dataset으로 fit했다.
        "train_record_count": len(dataset),
        # 다섯 검증 분할의 행 수 평균을 DB 정수 컬럼에 맞춰 반올림한다.
        "validation_record_count": validation_summary[
            "validation_record_count"
        ],
        "train_mae": final_train_metrics["mae"],
        "train_rmse": final_train_metrics["rmse"],
        "train_r2": final_train_metrics["r2"],
        "validation_mae": (
            validation_summary["validation"]["mae"]
        ),
        "validation_rmse": (
            validation_summary["validation"]["rmse"]
        ),
        "validation_r2": (
            validation_summary["validation"]["r2"]
        ),
    }

    artifact_id = insert_model_artifact(
        artifact_data=artifact_data,
    )

    logger.info(
        "모델 아티팩트 적재 완료: artifact_id=%d, "
        "model_variant=%s, model_version=%d, path=%s",
        artifact_id,
        model_variant,
        model_version,
        saved_path,
    )

    # 호출자가 저장 결과와 모델별 평가 지표를 함께 확인할 수 있도록
    # 모델 객체가 아닌 작은 메타데이터만 반환한다
    return {
        "artifact_id": artifact_id,
        "model_variant": model_variant,
        "model_version": model_version,
        "saved_path": saved_path,
        "train": final_train_metrics,
        "validation": validation_summary["validation"],
        "validation_folds": validation_summary["folds"],
    }


def run_all_model_training() -> dict[str, dict]:
    """공유 날짜 분할로 검증한 뒤 두 방향의 학습 대상 모델을 만든다."""
    results = {}
    datasets = _load_training_datasets()
    shared_date_splits = _create_shared_validation_splits(datasets)

    logger.info(
        "전체 모델 학습 시작: model_count=%d",
        len(MODEL_TRAINING_CONFIGS),
    )

    for config in MODEL_TRAINING_CONFIGS:
        model_variant = config["model_variant"]

        try:
            results[model_variant] = run_train_model(
                dataset=datasets[model_variant],
                shared_date_splits=shared_date_splits,
                model_variant=model_variant,
                model_version=config["model_version"],
                model_output_path=config[
                    "model_output_path"
                ],
            )

        except Exception:
            logger.exception(
                "모델 학습 실패: model_variant=%s, "
                "model_version=%d, path=%s",
                model_variant,
                config["model_version"],
                config["model_output_path"],
            )
            raise

    logger.info(
        "전체 모델 학습 완료: success_count=%d",
        len(results),
    )

    return results


def main() -> None:
    results = run_all_model_training()

    logger.info(
        "학습 실행 종료: artifacts=%s",
        {
            model_variant: result["artifact_id"]
            for model_variant, result in results.items()
        },
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
