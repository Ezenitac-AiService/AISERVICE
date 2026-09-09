import json

from pathlib import Path
from typing import Any

from pilos.analysis.signal_calibration import (
    MODEL_VARIANTS,
    SIGNAL_CALIBRATION_SCHEMA_VERSION,
)
from pilos.dto.comment_signal_dto import (
    SignalCalibration,
    VariantCalibration,
)


BASE_DIR = Path(__file__).resolve().parents[2]

# calibration은 재추론 원본이 아니라 모델 artifact 성격의 메타데이터다.
# 따라서 운영 DB가 아니라 Git 비추적 artifacts 경로에 보관한다.
CALIBRATION_DIR = BASE_DIR / "artifacts" / "calibration"


def resolve_calibration_path(
    *,
    model_name: str,
    model_version: int,
    calibration_dir: Path = CALIBRATION_DIR,
) -> Path:
    """모델명·버전과 1:1로 대응하는 calibration 파일 경로를 만든다."""
    if not isinstance(model_name, str) or not model_name.strip():
        raise ValueError("model_name은 비어 있지 않은 문자열이어야 합니다.")

    if (
        not isinstance(model_version, int)
        or isinstance(model_version, bool)
        or model_version <= 0
    ):
        raise ValueError("model_version은 1 이상의 정수여야 합니다.")

    file_name = (
        f"{model_name.strip()}_v{model_version}_signal_calibration.json"
    )
    return calibration_dir / file_name


def _calibration_to_json(
    calibration: SignalCalibration,
) -> dict[str, Any]:
    return {
        "calibration_schema_version": (
            calibration.calibration_schema_version
        ),
        "generated_at": calibration.generated_at,
        "source_scope": calibration.source_scope,
        "source_row_count": calibration.source_row_count,
        "model_name": calibration.model_name,
        "model_version": calibration.model_version,
        "artifact_type": calibration.artifact_type,
        "artifact_schema_version": calibration.artifact_schema_version,
        "tokenizer_version": calibration.tokenizer_version,
        "vectorizer_name": calibration.vectorizer_name,
        "scaler_name": calibration.scaler_name,
        "dataset_start_date": calibration.dataset_start_date,
        "dataset_end_date": calibration.dataset_end_date,
        "variants": {
            variant.model_variant: {
                "artifact_id": variant.artifact_id,
                "sample_count": variant.sample_count,
                "quantile_levels": list(variant.quantile_levels),
                "quantile_scores": list(variant.quantile_scores),
            }
            for variant in calibration.variants
        },
    }


def save_signal_calibration(
    *,
    calibration: SignalCalibration,
    output_path: str | Path,
    overwrite: bool = False,
) -> Path:
    """
    calibration 메타데이터를 JSON artifact로 저장한다.

    기존 파일을 기본적으로 덮어쓰지 않는다. 모델 재학습으로 분포가
    바뀌었다면 새 model_version 경로에 저장한다.
    """
    path = Path(output_path)

    if path.suffix.lower() != ".json":
        raise ValueError("calibration artifact는 .json으로 저장해야 합니다.")

    if path.exists() and not overwrite:
        raise FileExistsError(
            f"기존 calibration artifact를 덮어쓰지 않습니다: {path}"
        )

    payload = _calibration_to_json(calibration)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    return path


def load_signal_calibration(
    calibration_path: str | Path,
) -> SignalCalibration:
    """
    저장된 calibration artifact를 복원하고 구조 계약을 검증한다.

    백분위 배열의 길이·단조성까지 확인하여 손상된 파일로 잘못된 신호를
    만들지 않도록 한다.
    """
    path = Path(calibration_path)

    if not path.exists():
        raise FileNotFoundError(
            f"calibration artifact가 없습니다: {path}"
        )

    payload = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(payload, dict):
        raise ValueError("calibration artifact는 JSON 객체여야 합니다.")

    schema_version = payload.get("calibration_schema_version")

    if schema_version != SIGNAL_CALIBRATION_SCHEMA_VERSION:
        raise ValueError(
            "지원하지 않는 calibration 스키마 버전입니다: "
            f"{schema_version}"
        )

    raw_variants = payload.get("variants")

    if not isinstance(raw_variants, dict):
        raise ValueError("calibration variants는 객체여야 합니다.")

    if set(raw_variants.keys()) != set(MODEL_VARIANTS):
        raise ValueError(
            "calibration에는 positive와 negative가 모두 있어야 합니다."
        )

    variants = tuple(
        _variant_from_json(
            model_variant=model_variant,
            raw_variant=raw_variants[model_variant],
        )
        for model_variant in MODEL_VARIANTS
    )
    return SignalCalibration(
        calibration_schema_version=int(schema_version),
        generated_at=str(payload["generated_at"]),
        source_scope=str(payload["source_scope"]),
        source_row_count=int(payload["source_row_count"]),
        model_name=str(payload["model_name"]),
        model_version=int(payload["model_version"]),
        artifact_type=str(payload["artifact_type"]),
        artifact_schema_version=int(payload["artifact_schema_version"]),
        tokenizer_version=str(payload["tokenizer_version"]),
        vectorizer_name=str(payload["vectorizer_name"]),
        scaler_name=str(payload["scaler_name"]),
        dataset_start_date=str(payload["dataset_start_date"]),
        dataset_end_date=str(payload["dataset_end_date"]),
        variants=variants,
    )


def _variant_from_json(
    *,
    model_variant: str,
    raw_variant: Any,
) -> VariantCalibration:
    if not isinstance(raw_variant, dict):
        raise ValueError("calibration variant는 객체여야 합니다.")

    quantile_levels = raw_variant.get("quantile_levels")
    quantile_scores = raw_variant.get("quantile_scores")

    if (
        not isinstance(quantile_levels, list)
        or not isinstance(quantile_scores, list)
        or len(quantile_levels) != len(quantile_scores)
        or len(quantile_levels) < 2
    ):
        raise ValueError(
            "calibration 백분위 배열 구조가 올바르지 않습니다: "
            f"variant={model_variant}"
        )

    levels = tuple(float(level) for level in quantile_levels)
    scores = tuple(float(score) for score in quantile_scores)

    if any(
        later < earlier
        for earlier, later in zip(levels, levels[1:])
    ):
        raise ValueError(
            "calibration 백분위 지점이 오름차순이 아닙니다: "
            f"variant={model_variant}"
        )

    if any(
        later < earlier
        for earlier, later in zip(scores, scores[1:])
    ):
        raise ValueError(
            "calibration 백분위 점수가 비내림차순이 아닙니다: "
            f"variant={model_variant}"
        )

    return VariantCalibration(
        model_variant=model_variant,
        artifact_id=int(raw_variant["artifact_id"]),
        sample_count=int(raw_variant["sample_count"]),
        quantile_levels=levels,
        quantile_scores=scores,
    )
