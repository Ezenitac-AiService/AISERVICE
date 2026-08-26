import json

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from pilos.analysis.modeling.model_inference import (
    analyze_text_contributions,
    split_text_only_ridge_coefficients,
)
from pilos.analysis.tokenizer_settings import (
    TOKENIZER_VERSION,
)
from pilos.model_config import (
    ACTIVE_SERVICE_MODEL_VERSION,
    MIN_RECOGNIZED_FEATURE_COUNT,
    MIN_VOCABULARY_COVERAGE,
    SERVICE_INFERENCE_START_DATE,
    SERVICE_MODEL_ARTIFACT_SCHEMA_VERSION as ARTIFACT_SCHEMA_VERSION,
    SERVICE_MODEL_NAME as MODEL_NAME,
    SERVICE_MODEL_VARIANTS,
)
from pilos.storage.model_artifacts import (
    load_registered_model_artifacts as load_registered_artifact_bundle,
    resolve_registered_model_path,
)
from pilos.storage.model_inference_db import (
    insert_sentiment_index_results,
    select_daily_documents_for_inference,
)
from pilos.storage.model_training_db import (
    SupplyDirection,
)

# CLI:
# uv run python -m pilos.jobs.predict_model

BASE_DIR = Path(__file__).resolve().parents[2]
INFERENCE_START_DATE = SERVICE_INFERENCE_START_DATE
TOP_N = 10

# 텍스트 정보가 지나치게 적은 문서는 예측 자체는 계산하되 이후 화면
# 계층에서 숨길 수 있도록 결과 상태를 insufficient_features로 표시한다.


def get_current_kst_date() -> date:
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


def load_registered_model_artifacts(
    *,
    model_variant: SupplyDirection,
    model_version: int,
) -> tuple[dict, dict]:
    """
    DB에 등록된 정확한 모델 버전의 경로로 v2 bundle을 불러온다.

    입력:
    - model_variant: positive 또는 negative 수급 방향이다.
    - model_version: MODEL_TRAINING_CONFIGS에 고정된 서비스 버전이다.

    출력:
    - 첫 번째 dict는 DB artifacts 행, 두 번째 dict는 검증된 로컬 모델
      bundle이다.

    DB 정보와 bundle의 모델명·방향·버전·토크나이저·Dataset 기간이
    하나라도 다르면 다른 모델 파일이 연결된 것으로 판단해 차단한다.
    """
    return load_registered_artifact_bundle(
        model_name=MODEL_NAME,
        model_variant=model_variant,
        model_version=model_version,
        artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
        base_dir=BASE_DIR,
    )


def run_text_only_inference(
    *,
    daily_documents: list[dict],
    artifact_record: dict,
    model_artifacts: dict,
    top_n: int = 10,
) -> list[dict]:
    """
    한 방향의 text-only Ridge로 일별문서 목록을 추론한다.

    입력:
    - daily_documents: DB에서 조회한 최신 종목·날짜별 일별문서다.
    - artifact_record: 결과에 artifact_id와 모델 정보를 연결할 DB 행이다.
    - model_artifacts: 로더 검증을 통과한 Vectorizer·Ridge bundle이다.
    - top_n: 문서별 양수·음수 contribution에서 각각 반환할 최대
      키워드 수다.

    출력:
    - 각 문서의 방향별 예측지수, 절편, 텍스트 점수, vocabulary 인식
      상태와 키워드 contribution을 포함한 dict 목록을 반환한다.

    이 함수는 결과를 저장하지 않는다. 동일 입력과 모델 bundle이면 같은
    결과를 반환하며 DB 저장은 다음 작업 범위에서 별도 구성한다.
    """
    if top_n <= 0:
        raise ValueError(
            "top_n은 1 이상이어야 합니다."
        )

    inference_df = pd.DataFrame.from_records(
        daily_documents
    )

    if inference_df.empty:
        raise ValueError(
            "추론할 일별문서가 없습니다."
        )

    required_columns = {
        "daily_document_id",
        "stock_code",
        "model_date",
        "tfidf_text",
        "comment_count",
    }
    missing_columns = (
        required_columns
        - set(inference_df.columns)
    )

    if missing_columns:
        raise ValueError(
            "추론 일별문서에 필요한 컬럼이 없습니다: "
            f"{sorted(missing_columns)}"
        )

    if inference_df[
        [
            "daily_document_id",
            "stock_code",
            "model_date",
            "tfidf_text",
            "comment_count",
        ]
    ].isna().any().any():
        raise ValueError(
            "추론 일별문서의 필수값에 결측이 있습니다."
        )

    if not inference_df["stock_code"].map(
        lambda value: isinstance(value, str)
    ).all():
        raise ValueError(
            "stock_code는 문자열이어야 합니다."
        )

    if not inference_df["tfidf_text"].map(
        lambda value: isinstance(value, str)
    ).all():
        raise ValueError(
            "tfidf_text는 문자열이어야 합니다."
        )

    vectorizer = model_artifacts["vectorizer"]
    ridge_model = model_artifacts["ridge_model"]
    inference_features = vectorizer.transform(
        inference_df["tfidf_text"]
    )
    predictions = ridge_model.predict(
        inference_features
    )

    if not np.isfinite(predictions).all():
        raise ValueError(
            "모델 예측값에 유한하지 않은 값이 있습니다."
        )

    feature_names = vectorizer.get_feature_names_out()
    text_coefficients, intercept = (
        split_text_only_ridge_coefficients(
            model=ridge_model,
            text_feature_count=len(feature_names),
        )
    )
    recognized_feature_counts = np.asarray(
        inference_features.getnnz(axis=1)
    ).reshape(-1)
    results = []

    for row_index in range(len(inference_df)):
        text_analysis = analyze_text_contributions(
            tfidf_row=inference_features.getrow(
                row_index
            ),
            feature_names=feature_names,
            text_coefficients=text_coefficients,
            top_n=top_n,
        )
        predicted_index = float(
            predictions[row_index]
        )
        reconstructed_prediction = (
            intercept + text_analysis["text_score"]
        )

        if not np.isclose(
            predicted_index,
            reconstructed_prediction,
        ):
            raise RuntimeError(
                "예측값과 절편·텍스트 contribution 합이 다릅니다."
            )

        metadata = inference_df.iloc[row_index]
        unique_token_count = len(
            set(metadata["tfidf_text"].split())
        )
        recognized_feature_count = int(
            recognized_feature_counts[row_index]
        )
        vocabulary_coverage = (
            recognized_feature_count
            / unique_token_count
            if unique_token_count > 0
            else 0.0
        )
        inference_status = "ready"

        if (
            recognized_feature_count
            < MIN_RECOGNIZED_FEATURE_COUNT
            or vocabulary_coverage
            < MIN_VOCABULARY_COVERAGE
        ):
            inference_status = (
                "insufficient_features"
            )

        results.append(
            {
                "daily_document_id": int(
                    metadata["daily_document_id"]
                ),
                "stock_code": metadata["stock_code"],
                "model_date": metadata["model_date"],
                "comment_count": int(
                    metadata["comment_count"]
                ),
                "artifact_id": int(
                    artifact_record["artifact_id"]
                ),
                "model_name": artifact_record[
                    "model_name"
                ],
                "model_variant": artifact_record[
                    "model_variant"
                ],
                "model_version": int(
                    artifact_record["model_version"]
                ),
                "predicted_supply_demand_index": (
                    predicted_index
                ),
                "intercept": intercept,
                "text_score": text_analysis[
                    "text_score"
                ],
                "recognized_feature_count": (
                    recognized_feature_count
                ),
                "unique_token_count": (
                    unique_token_count
                ),
                "vocabulary_coverage": float(
                    vocabulary_coverage
                ),
                "inference_status": inference_status,
                "positive_keywords": text_analysis[
                    "positive_keywords"
                ],
                "negative_keywords": text_analysis[
                    "negative_keywords"
                ],
            }
        )

    return results


def run_database_inference(
    *,
    inference_start_date: date,
    inference_end_date: date,
    top_n: int = 10,
) -> tuple[
    dict[SupplyDirection, list[dict]],
    dict[str, int],
]:
    """
    DB 일별문서를 등록된 Positive·Negative 모델로 각각 추론한다.

    입력:
    - inference_start_date, inference_end_date: DB에서 읽을 일별문서의
      포함 기간이다.
    - top_n: 각 모델·문서에서 반환할 방향별 키워드 최대 개수다.

    출력:
    - 첫 번째 값은 positive와 negative별 추론 결과 목록이다.
    - 두 번째 값은 전체 입력·신규 적재·기존 결과 제외 수다.

    일별문서는 한 번만 조회하고 두 모델이 같은 입력을 공유한다. 모델은
    MODEL_TRAINING_CONFIGS의 명시된 버전을 DB에서 각각 조회한다. 두 모델
    추론이 모두 성공한 뒤 결과 전체를 한 트랜잭션으로 DB에 적재한다.
    모델 로드·추론·적재 실패는 호출자에게 그대로 전달하여 후속 실행을
    중단할 수 있게 한다.
    """
    if inference_start_date < SERVICE_INFERENCE_START_DATE:
        raise ValueError(
            "자동 추론 시작일보다 이전 기간은 실행할 수 없습니다."
        )

    active_artifacts: dict[SupplyDirection, tuple[dict, dict]] = {}

    for model_variant in SERVICE_MODEL_VARIANTS:
        active_artifacts[model_variant] = load_registered_model_artifacts(
            model_variant=model_variant,
            model_version=ACTIVE_SERVICE_MODEL_VERSION,
        )

    daily_documents = (
        select_daily_documents_for_inference(
            tokenizer_version=TOKENIZER_VERSION,
            inference_start_date=(
                inference_start_date
            ),
            inference_end_date=inference_end_date,
            artifact_ids=tuple(
                artifact_record["artifact_id"]
                for artifact_record, _ in active_artifacts.values()
            ),
        )
    )

    if not daily_documents:
        return (
            {model_variant: [] for model_variant in SERVICE_MODEL_VARIANTS},
            {
                "input_count": 0,
                "inserted_count": 0,
                "existing_count": 0,
            },
        )

    results: dict[
        SupplyDirection,
        list[dict],
    ] = {}

    for model_variant in SERVICE_MODEL_VARIANTS:
        artifact_record, model_artifacts = active_artifacts[model_variant]
        results[model_variant] = run_text_only_inference(
            daily_documents=daily_documents,
            artifact_record=artifact_record,
            model_artifacts=model_artifacts,
            top_n=top_n,
        )

    all_inference_results = [
        inference_result
        for model_results in results.values()
        for inference_result in model_results
    ]
    storage_summary = insert_sentiment_index_results(
        inference_results=all_inference_results,
    )

    return results, storage_summary


def main() -> None:
    """설정 기간의 DB 일별문서를 두 선정 모델로 추론하고 요약한다."""
    inference_end_date = get_current_kst_date()
    results, storage_summary = run_database_inference(
        inference_start_date=INFERENCE_START_DATE,
        inference_end_date=inference_end_date,
        top_n=TOP_N,
    )
    summary = {
        "inference_start_date": INFERENCE_START_DATE,
        "inference_end_date": inference_end_date,
        "storage": storage_summary,
        "models": {},
    }

    for model_variant, model_results in results.items():
        first_result = model_results[0] if model_results else None
        summary["models"][model_variant] = {
            "artifact_id": (
                first_result["artifact_id"] if first_result else None
            ),
            "model_version": (
                first_result["model_version"]
                if first_result
                else ACTIVE_SERVICE_MODEL_VERSION
            ),
            "result_count": len(model_results),
            "ready_count": sum(
                result["inference_status"]
                == "ready"
                for result in model_results
            ),
            "insufficient_feature_count": sum(
                result["inference_status"]
                == "insufficient_features"
                for result in model_results
            ),
        }

    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
