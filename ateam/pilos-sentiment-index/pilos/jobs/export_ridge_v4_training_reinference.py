import argparse
import json
import math

from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pandas as pd

from pilos.jobs.predict_model import (
    load_registered_model_artifacts,
    run_text_only_inference,
)
from pilos.storage.model_training_db import (
    select_daily_document_stock_metadata,
    select_model_training_records,
)


BASE_DIR = Path(__file__).resolve().parents[2]
TRAINING_END_DATE = date(2026, 7, 24)
MODEL_VARIANTS = ("positive", "negative")
MODEL_VERSION = 4
TOP_N = 10
DEFAULT_CSV_PATH = (
    BASE_DIR / "data" / "analysis" / "ridge_v4_training_reinference.csv"
)
DEFAULT_SUMMARY_PATH = (
    BASE_DIR
    / "data"
    / "analysis"
    / "ridge_v4_training_reinference_summary.json"
)
CSV_COLUMNS = (
    "daily_document_id",
    "stock_id",
    "stock_code",
    "stock_name",
    "model_date",
    "comment_count",
    "dataset_split",
    "was_used_for_training",
    "actual_target",
    "artifact_id",
    "artifact_type",
    "model_name",
    "model_variant",
    "model_version",
    "artifact_schema_version",
    "tokenizer_version",
    "vectorizer_name",
    "scaler_name",
    "dataset_start_date",
    "dataset_end_date",
    "predicted_score",
    "intercept",
    "text_score",
    "comment_count_contribution",
    "recognized_feature_count",
    "prediction_error",
    "absolute_error",
    "positive_contribution_keywords",
    "negative_contribution_keywords",
    "inference_created_at",
    "source_scope",
)


def _normalize_model_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    try:
        return date.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError(f"model_date를 날짜로 변환할 수 없습니다: {value!r}") from error


def _isoformat_date(value: Any) -> str:
    """artifacts 행의 Dataset 기간을 CSV 문자열로 변환한다."""
    return _normalize_model_date(value).isoformat()


def _finite_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name}는 유한한 숫자여야 합니다.")

    try:
        converted = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name}는 유한한 숫자여야 합니다.") from error

    if not math.isfinite(converted):
        raise ValueError(f"{field_name}는 유한한 숫자여야 합니다.")

    return converted


def _validate_keyword_directions(
    *,
    positive_keywords: list[dict],
    negative_keywords: list[dict],
) -> None:
    required_fields = {"rank", "word", "tfidf", "coefficient", "contribution"}

    for keywords, expected_sign in (
        (positive_keywords, 1),
        (negative_keywords, -1),
    ):
        if not isinstance(keywords, list):
            raise ValueError("기여 키워드는 목록이어야 합니다.")

        for keyword in keywords:
            if not isinstance(keyword, dict) or required_fields - keyword.keys():
                raise ValueError("기여 키워드 필드가 기존 추론 계약과 다릅니다.")

            contribution = _finite_float(
                keyword["contribution"],
                "keyword.contribution",
            )

            if expected_sign > 0 and contribution <= 0:
                raise ValueError("positive 키워드 contribution은 양수여야 합니다.")

            if expected_sign < 0 and contribution >= 0:
                raise ValueError("negative 키워드 contribution은 음수여야 합니다.")

            _finite_float(keyword["tfidf"], "keyword.tfidf")
            _finite_float(keyword["coefficient"], "keyword.coefficient")


def _json_cell(value: list[dict]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def _load_training_scope(
    *,
    training_end_date: date,
    select_training_records: Callable[..., list[dict]],
) -> tuple[list[dict], dict[str, dict[int, float]]]:
    targets: dict[int, dict] = {}
    actual_targets: dict[str, dict[int, float]] = {
        variant: {}
        for variant in MODEL_VARIANTS
    }

    for model_variant in MODEL_VARIANTS:
        records = select_training_records(
            tokenizer_version="kiwi_ver1",
            training_end_date=training_end_date,
            supply_direction=model_variant,
        )

        if not records:
            raise ValueError(f"{model_variant} 방향의 학습 데이터가 없습니다.")

        for record in records:
            daily_document_id = int(record["daily_document_id"])

            if daily_document_id in actual_targets[model_variant]:
                raise ValueError(
                    "학습 Dataset에 같은 방향의 daily_document가 중복됐습니다: "
                    f"daily_document_id={daily_document_id}, variant={model_variant}"
                )

            actual_target = _finite_float(
                record["supply_demand_index"],
                "supply_demand_index",
            )

            if model_variant == "positive" and actual_target <= 0:
                raise ValueError("Positive 학습 목표값은 0보다 커야 합니다.")

            if model_variant == "negative" and actual_target >= 0:
                raise ValueError("Negative 학습 목표값은 0보다 작아야 합니다.")

            actual_targets[model_variant][daily_document_id] = actual_target
            normalized = {
                "daily_document_id": daily_document_id,
                "stock_code": str(record["stock_code"]),
                "model_date": _normalize_model_date(record["model_date"]),
                "tfidf_text": record["tfidf_text"],
                "comment_count": int(record["comment_count"]),
            }
            existing = targets.get(daily_document_id)

            if existing is not None and existing != normalized:
                raise ValueError(
                    "방향별 학습 Dataset의 같은 daily_document 내용이 다릅니다: "
                    f"daily_document_id={daily_document_id}"
                )

            targets[daily_document_id] = normalized

    ordered_targets = sorted(
        targets.values(),
        key=lambda row: (
            row["model_date"],
            row["stock_code"],
            row["daily_document_id"],
        ),
    )
    return ordered_targets, actual_targets


def _build_export_row(
    *,
    inference_result: dict,
    target: dict,
    stock_metadata: dict,
    artifact_record: dict,
    actual_target: float | None,
    inference_created_at: str,
    source_scope: str,
) -> dict[str, Any]:
    predicted_score = _finite_float(
        inference_result["predicted_supply_demand_index"],
        "predicted_score",
    )
    intercept = _finite_float(inference_result["intercept"], "intercept")
    text_score = _finite_float(inference_result["text_score"], "text_score")
    comment_count_contribution = 0.0

    if not math.isclose(
        predicted_score,
        intercept + text_score + comment_count_contribution,
        rel_tol=1e-9,
        abs_tol=1e-9,
    ):
        raise ValueError(
            "예측값이 절편·텍스트·댓글 수 contribution 합과 다릅니다: "
            f"daily_document_id={target['daily_document_id']}, "
            f"variant={artifact_record['model_variant']}"
        )

    positive_keywords = inference_result["positive_keywords"]
    negative_keywords = inference_result["negative_keywords"]
    _validate_keyword_directions(
        positive_keywords=positive_keywords,
        negative_keywords=negative_keywords,
    )
    prediction_error = (
        None
        if actual_target is None
        else predicted_score - actual_target
    )
    return {
        "daily_document_id": target["daily_document_id"],
        "stock_id": int(stock_metadata["stock_id"]),
        "stock_code": target["stock_code"],
        "stock_name": stock_metadata["stock_name"],
        "model_date": target["model_date"].isoformat(),
        "comment_count": target["comment_count"],
        "dataset_split": "train" if actual_target is not None else None,
        "was_used_for_training": actual_target is not None,
        "actual_target": actual_target,
        "artifact_id": int(artifact_record["artifact_id"]),
        "artifact_type": artifact_record["artifact_type"],
        "model_name": artifact_record["model_name"],
        "model_variant": artifact_record["model_variant"],
        "model_version": int(artifact_record["model_version"]),
        "artifact_schema_version": int(artifact_record["artifact_schema_version"]),
        "tokenizer_version": artifact_record["tokenizer_version"],
        "vectorizer_name": artifact_record["vectorizer_name"],
        "scaler_name": artifact_record["scaler_name"],
        "dataset_start_date": _isoformat_date(
            artifact_record["dataset_start_date"]
        ),
        "dataset_end_date": _isoformat_date(
            artifact_record["dataset_end_date"]
        ),
        "predicted_score": predicted_score,
        "intercept": intercept,
        "text_score": text_score,
        "comment_count_contribution": comment_count_contribution,
        "recognized_feature_count": int(
            inference_result["recognized_feature_count"]
        ),
        "prediction_error": prediction_error,
        "absolute_error": (
            None
            if prediction_error is None
            else abs(prediction_error)
        ),
        "positive_contribution_keywords": _json_cell(positive_keywords),
        "negative_contribution_keywords": _json_cell(negative_keywords),
        "inference_created_at": inference_created_at,
        "source_scope": source_scope,
    }


def _validate_export_rows(rows: list[dict], document_ids: set[int]) -> None:
    keys = [
        (row["daily_document_id"], row["model_variant"])
        for row in rows
    ]

    if len(keys) != len(set(keys)):
        raise ValueError("CSV 결과에 daily_document·model_variant 중복이 있습니다.")

    expected_keys = {
        (daily_document_id, model_variant)
        for daily_document_id in document_ids
        for model_variant in MODEL_VARIANTS
    }

    if set(keys) != expected_keys:
        raise ValueError("모든 일별문서에 Positive·Negative 결과가 한 건씩 없습니다.")


def _distribution_summary(scores: pd.Series) -> dict[str, int | float]:
    return {
        "count": int(scores.count()),
        "min": float(scores.min()),
        "max": float(scores.max()),
        "mean": float(scores.mean()),
        "median": float(scores.median()),
        "std": float(scores.std(ddof=0)),
        "q10": float(scores.quantile(0.10)),
        "q20": float(scores.quantile(0.20)),
        "q25": float(scores.quantile(0.25)),
        "q50": float(scores.quantile(0.50)),
        "q75": float(scores.quantile(0.75)),
        "q80": float(scores.quantile(0.80)),
        "q90": float(scores.quantile(0.90)),
    }


def export_ridge_v4_training_reinference(
    *,
    training_end_date: date = TRAINING_END_DATE,
    csv_path: Path = DEFAULT_CSV_PATH,
    summary_path: Path = DEFAULT_SUMMARY_PATH,
    select_training_records: Callable[..., list[dict]] = (
        select_model_training_records
    ),
    select_stock_metadata: Callable[..., dict[int, dict]] = (
        select_daily_document_stock_metadata
    ),
    load_artifacts: Callable[..., tuple[dict, dict]] = (
        load_registered_model_artifacts
    ),
    run_inference: Callable[..., list[dict]] = run_text_only_inference,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """최종 Ridge v4로 전체 학습 범위를 재추론해 CSV와 요약 JSON을 만든다."""
    if csv_path.exists() or summary_path.exists():
        existing = [
            str(path)
            for path in (csv_path, summary_path)
            if path.exists()
        ]
        raise FileExistsError(f"기존 분석 산출물을 덮어쓰지 않습니다: {existing}")

    targets, actual_targets = _load_training_scope(
        training_end_date=training_end_date,
        select_training_records=select_training_records,
    )
    document_ids = {
        target["daily_document_id"]
        for target in targets
    }
    metadata_by_document = select_stock_metadata(
        daily_document_ids=sorted(document_ids)
    )
    missing_metadata = document_ids - metadata_by_document.keys()

    if missing_metadata:
        raise ValueError(
            "종목 메타데이터를 찾지 못한 일별문서가 있습니다: "
            f"{sorted(missing_metadata)}"
        )

    generated_at = generated_at or datetime.now(ZoneInfo("Asia/Seoul"))
    inference_created_at = generated_at.isoformat()
    source_scope = (
        "training_dataset_reinference_until_"
        f"{training_end_date.isoformat()}"
    )
    rows = []

    for model_variant in MODEL_VARIANTS:
        artifact_record, model_artifacts = load_artifacts(
            model_variant=model_variant,
            model_version=MODEL_VERSION,
        )

        if artifact_record["dataset_end_date"] != training_end_date:
            raise ValueError(
                "아티팩트 학습 종료일과 요청한 Dataset 종료일이 다릅니다: "
                f"variant={model_variant}, "
                f"artifact={artifact_record['dataset_end_date']}, "
                f"requested={training_end_date}"
            )
        inference_results = run_inference(
            daily_documents=targets,
            artifact_record=artifact_record,
            model_artifacts=model_artifacts,
            top_n=TOP_N,
        )
        results_by_document = {
            int(result["daily_document_id"]): result
            for result in inference_results
        }

        if len(results_by_document) != len(inference_results):
            raise ValueError(f"{model_variant} 추론 결과에 문서 중복이 있습니다.")

        if results_by_document.keys() != document_ids:
            raise ValueError(f"{model_variant} 추론 결과의 문서 범위가 다릅니다.")

        for target in targets:
            daily_document_id = target["daily_document_id"]
            rows.append(
                _build_export_row(
                    inference_result=results_by_document[daily_document_id],
                    target=target,
                    stock_metadata=metadata_by_document[daily_document_id],
                    artifact_record=artifact_record,
                    actual_target=actual_targets[model_variant].get(
                        daily_document_id
                    ),
                    inference_created_at=inference_created_at,
                    source_scope=source_scope,
                )
            )

    _validate_export_rows(rows, document_ids)
    rows.sort(
        key=lambda row: (
            row["model_date"],
            row["stock_code"],
            row["daily_document_id"],
            MODEL_VARIANTS.index(row["model_variant"]),
        )
    )
    dataframe = pd.DataFrame.from_records(rows, columns=CSV_COLUMNS)
    summary = {
        "generated_at": inference_created_at,
        "document_count": len(document_ids),
        "row_count": len(rows),
        "stock_count": int(dataframe["stock_id"].nunique()),
        "start_date": str(dataframe["model_date"].min()),
        "end_date": str(dataframe["model_date"].max()),
    }

    for model_variant in MODEL_VARIANTS:
        scores = dataframe.loc[
            dataframe["model_variant"] == model_variant,
            "predicted_score",
        ]
        summary[model_variant] = _distribution_summary(scores)

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(
        csv_path,
        index=False,
        columns=CSV_COLUMNS,
        encoding="utf-8",
        na_rep="",
    )
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return summary


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("날짜는 YYYY-MM-DD 형식이어야 합니다.") from error


def main() -> None:
    parser = argparse.ArgumentParser(
        description="최종 Ridge v4의 전체 학습 범위 재추론 결과를 CSV로 저장합니다."
    )
    parser.add_argument(
        "--training-end-date",
        type=_parse_date,
        default=TRAINING_END_DATE,
    )
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--summary-path", type=Path, default=DEFAULT_SUMMARY_PATH)
    arguments = parser.parse_args()
    summary = export_ridge_v4_training_reinference(
        training_end_date=arguments.training_end_date,
        csv_path=arguments.csv_path,
        summary_path=arguments.summary_path,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
