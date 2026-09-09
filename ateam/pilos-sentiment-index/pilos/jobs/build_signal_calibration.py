import argparse
import json

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from pilos.analysis.signal_calibration import (
    MODEL_VARIANTS,
    SIGNAL_CALIBRATION_SCHEMA_VERSION,
    build_variant_calibration,
)
from pilos.dto.comment_signal_dto import SignalCalibration
from pilos.jobs.export_ridge_v4_training_reinference import (
    DEFAULT_CSV_PATH,
)
from pilos.storage.signal_calibration_store import (
    resolve_calibration_path,
    save_signal_calibration,
)


# CLI:
# uv run python -m pilos.jobs.build_signal_calibration
#
# 이 job은 export_ridge_v4_training_reinference가 만든 재추론 CSV만
# 입력으로 사용한다. 재추론 전체 행은 운영 DB에 적재하지 않으며 여기서
# 만드는 백분위 메타데이터만 artifact로 보관한다.

REQUIRED_CSV_COLUMNS = (
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
    "source_scope",
)
_SINGLE_VALUE_COLUMNS = (
    "artifact_type",
    "model_name",
    "model_version",
    "artifact_schema_version",
    "tokenizer_version",
    "vectorizer_name",
    "scaler_name",
    "dataset_start_date",
    "dataset_end_date",
    "source_scope",
)


def _single_value(
    dataframe: pd.DataFrame,
    column: str,
) -> Any:
    """재추론 CSV 전체에서 하나여야 하는 식별 값을 확인하고 반환한다."""
    values = dataframe[column].where(dataframe[column].notna(), None)
    unique_values = list(dict.fromkeys(values.tolist()))

    if len(unique_values) != 1:
        raise ValueError(
            "재추론 CSV에 서로 다른 모델 식별 값이 섞여 있습니다: "
            f"column={column}, values={unique_values}"
        )

    return unique_values[0]


def _required_text(value: Any, column: str) -> str:
    """
    calibration identity에 사용할 문자열 값을 확인한다.

    이 값들은 artifacts 테이블에 실제로 존재하는 컬럼이므로 비어 있으면
    잘못된 CSV로 판단하고 중단한다.
    """
    text = "" if value is None else str(value).strip()

    if not text:
        raise ValueError(
            f"재추론 CSV의 모델 식별 값이 비어 있습니다: column={column}"
        )

    return text


def build_signal_calibration(
    *,
    reinference_csv_path: Path = DEFAULT_CSV_PATH,
    output_path: Path | None = None,
    overwrite: bool = False,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """
    재추론 CSV의 실제 predicted_score 분포에서 calibration을 생성한다.

    입력:
    - reinference_csv_path: 현재 등록 모델로 학습 범위를 재추론한 CSV다.

    출력:
    - 저장 경로와 방향별 표본 수·분포 요약을 담은 dict를 반환한다.

    이 함수는 예시값이나 합성값을 절대 사용하지 않는다. CSV에 두 방향이
    모두 없거나 모델 식별 값이 섞여 있으면 오류로 중단한다.
    """
    csv_path = Path(reinference_csv_path)

    if not csv_path.exists():
        raise FileNotFoundError(
            "재추론 CSV가 없습니다. 먼저 "
            "pilos.jobs.export_ridge_v4_training_reinference를 실행하세요: "
            f"{csv_path}"
        )

    dataframe = pd.read_csv(csv_path)
    missing_columns = set(REQUIRED_CSV_COLUMNS) - set(dataframe.columns)

    if missing_columns:
        raise ValueError(
            "재추론 CSV에 필요한 컬럼이 없습니다: "
            f"{sorted(missing_columns)}"
        )

    if dataframe.empty:
        raise ValueError("재추론 CSV에 행이 없습니다.")

    observed_variants = set(dataframe["model_variant"].unique())

    if observed_variants != set(MODEL_VARIANTS):
        raise ValueError(
            "재추론 CSV에 positive와 negative가 모두 있어야 합니다: "
            f"{sorted(observed_variants)}"
        )

    if dataframe["predicted_score"].isna().any():
        raise ValueError("재추론 CSV의 predicted_score에 결측이 있습니다.")

    identity = {
        column: _single_value(dataframe, column)
        for column in _SINGLE_VALUE_COLUMNS
    }
    model_name = str(identity["model_name"]).strip()
    model_version = int(identity["model_version"])
    variants = []
    summary_by_variant: dict[str, dict[str, float | int]] = {}

    for model_variant in MODEL_VARIANTS:
        variant_frame = dataframe.loc[
            dataframe["model_variant"] == model_variant
        ]
        artifact_ids = sorted(
            {int(value) for value in variant_frame["artifact_id"]}
        )

        if len(artifact_ids) != 1:
            raise ValueError(
                "한 방향의 재추론 결과에 여러 artifact_id가 있습니다: "
                f"variant={model_variant}, artifact_ids={artifact_ids}"
            )

        variant_calibration = build_variant_calibration(
            model_variant=model_variant,
            artifact_id=artifact_ids[0],
            predicted_scores=variant_frame["predicted_score"].tolist(),
        )
        variants.append(variant_calibration)
        summary_by_variant[model_variant] = {
            "artifact_id": variant_calibration.artifact_id,
            "sample_count": variant_calibration.sample_count,
            "min": variant_calibration.quantile_scores[0],
            "median": variant_calibration.quantile_scores[
                len(variant_calibration.quantile_scores) // 2
            ],
            "max": variant_calibration.quantile_scores[-1],
        }

    generated_at = generated_at or datetime.now(ZoneInfo("Asia/Seoul"))
    calibration = SignalCalibration(
        calibration_schema_version=SIGNAL_CALIBRATION_SCHEMA_VERSION,
        generated_at=generated_at.isoformat(),
        source_scope=str(identity["source_scope"]),
        source_row_count=int(len(dataframe)),
        model_name=model_name,
        model_version=model_version,
        artifact_type=_required_text(identity["artifact_type"], "artifact_type"),
        artifact_schema_version=int(identity["artifact_schema_version"]),
        tokenizer_version=_required_text(
            identity["tokenizer_version"],
            "tokenizer_version",
        ),
        vectorizer_name=_required_text(
            identity["vectorizer_name"],
            "vectorizer_name",
        ),
        scaler_name=_required_text(identity["scaler_name"], "scaler_name"),
        dataset_start_date=_required_text(
            identity["dataset_start_date"],
            "dataset_start_date",
        ),
        dataset_end_date=_required_text(
            identity["dataset_end_date"],
            "dataset_end_date",
        ),
        variants=tuple(variants),
    )
    resolved_output_path = Path(
        output_path
        or resolve_calibration_path(
            model_name=model_name,
            model_version=model_version,
        )
    )
    saved_path = save_signal_calibration(
        calibration=calibration,
        output_path=resolved_output_path,
        overwrite=overwrite,
    )
    return {
        "calibration_path": str(saved_path),
        "calibration_schema_version": SIGNAL_CALIBRATION_SCHEMA_VERSION,
        "model_name": model_name,
        "model_version": model_version,
        "source_csv": str(csv_path),
        "source_scope": calibration.source_scope,
        "source_row_count": calibration.source_row_count,
        "variants": summary_by_variant,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "재추론 CSV에서 댓글 수급 신호 calibration artifact를 만듭니다."
        )
    )
    parser.add_argument(
        "--reinference-csv-path",
        type=Path,
        default=DEFAULT_CSV_PATH,
    )
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="같은 경로의 기존 calibration artifact를 교체합니다.",
    )
    arguments = parser.parse_args()
    summary = build_signal_calibration(
        reinference_csv_path=arguments.reinference_csv_path,
        output_path=arguments.output_path,
        overwrite=arguments.overwrite,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
