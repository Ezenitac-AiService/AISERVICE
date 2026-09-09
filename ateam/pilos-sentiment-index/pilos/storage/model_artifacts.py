import pickle

from datetime import date
from pathlib import Path
from typing import Literal

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge

from pilos.storage.model_training_db import (
    SupplyDirection,
    select_model_artifact,
)
from pilos.model_config import (
    REQUIRED_TOKENIZER_VERSION,
    SERVICE_MODEL_ARTIFACT_SCHEMA_VERSION,
)


MODEL_ARTIFACT_SCHEMA_VERSION = SERVICE_MODEL_ARTIFACT_SCHEMA_VERSION
ModelVariant = Literal[
    "positive",
    "negative",
]


def _validate_model_artifacts(
    artifacts: dict,
) -> dict:
    """
    text-only Ridge bundle의 필드·자료형·학습 상태를 검증한다.

    입력:
    - artifacts: 저장 전이거나 pickle에서 복원한 모델 bundle dict다.

    출력:
    - 모든 계약 검증을 통과한 원본 dict를 반환한다.

    검증 범위:
    - 스키마·모델·토크나이저 버전과 Dataset 기간
    - text_only 특성 모드와 Positive/Negative 모델 방향
    - 학습된 TF-IDF Vectorizer와 Ridge 모델의 실제 자료형
    - Vectorizer 특성 수와 Ridge 계수 수의 일치 여부
    """
    if not isinstance(artifacts, dict):
        raise ValueError(
            "모델 산출물의 구조가 올바르지 않습니다."
        )

    required_fields = {
        "artifact_schema_version",
        "model_name",
        "model_variant",
        "model_version",
        "feature_mode",
        "tokenizer_version",
        "dataset_start_date",
        "dataset_end_date",
        "vectorizer",
        "ridge_model",
    }
    missing_fields = required_fields - artifacts.keys()

    if missing_fields:
        raise ValueError(
            "모델 산출물에 필요한 필드가 없습니다: "
            f"{sorted(missing_fields)}"
        )

    unexpected_fields = artifacts.keys() - required_fields

    if unexpected_fields:
        raise ValueError(
            "모델 산출물 계약에 없는 필드가 있습니다: "
            f"{sorted(unexpected_fields)}"
        )

    if (
        artifacts["artifact_schema_version"]
        != MODEL_ARTIFACT_SCHEMA_VERSION
    ):
        raise ValueError(
            "지원하지 않는 모델 산출물 스키마 버전입니다."
        )

    model_name = artifacts["model_name"]

    if (
        not isinstance(model_name, str)
        or not model_name.strip()
    ):
        raise ValueError(
            "model_name은 비어 있지 않은 문자열이어야 합니다."
        )

    if artifacts["model_variant"] not in {
        "positive",
        "negative",
    }:
        raise ValueError(
            "model_variant는 positive 또는 negative여야 합니다."
        )

    model_version = artifacts["model_version"]

    if (
        not isinstance(model_version, int)
        or isinstance(model_version, bool)
        or model_version <= 0
    ):
        raise ValueError(
            "model_version은 1 이상의 정수여야 합니다."
        )

    if artifacts["feature_mode"] != "text_only":
        raise ValueError(
            "현재 스키마의 feature_mode는 text_only여야 합니다."
        )

    tokenizer_version = artifacts[
        "tokenizer_version"
    ]

    if (
        not isinstance(tokenizer_version, str)
        or not tokenizer_version.strip()
    ):
        raise ValueError(
            "tokenizer_version은 비어 있지 않은 문자열이어야 합니다."
        )

    dataset_start_date = artifacts[
        "dataset_start_date"
    ]
    dataset_end_date = artifacts[
        "dataset_end_date"
    ]

    if (
        not isinstance(dataset_start_date, date)
        or not isinstance(dataset_end_date, date)
    ):
        raise ValueError(
            "Dataset 시작일과 종료일은 date여야 합니다."
        )

    if dataset_start_date > dataset_end_date:
        raise ValueError(
            "Dataset 시작일은 종료일보다 늦을 수 없습니다."
        )

    vectorizer = artifacts["vectorizer"]
    ridge_model = artifacts["ridge_model"]

    if not isinstance(
        vectorizer,
        TfidfVectorizer,
    ):
        raise ValueError(
            "학습된 TfidfVectorizer가 없습니다."
        )

    if not hasattr(vectorizer, "vocabulary_"):
        raise ValueError(
            "학습되지 않은 TfidfVectorizer입니다."
        )

    if not isinstance(ridge_model, Ridge):
        raise ValueError(
            "학습된 Ridge 모델이 없습니다."
        )

    if (
        not hasattr(ridge_model, "coef_")
        or not hasattr(ridge_model, "intercept_")
    ):
        raise ValueError(
            "학습되지 않은 Ridge 모델입니다."
        )

    feature_names = vectorizer.get_feature_names_out()
    coefficients = np.asarray(
        ridge_model.coef_,
        dtype=float,
    ).reshape(-1)

    if feature_names.size != coefficients.size:
        raise ValueError(
            "TF-IDF 특성 수와 Ridge 계수 수가 다릅니다."
        )

    if not np.isfinite(coefficients).all():
        raise ValueError(
            "Ridge 계수에 유한하지 않은 값이 있습니다."
        )

    intercept_values = np.asarray(
        ridge_model.intercept_,
        dtype=float,
    ).reshape(-1)

    if (
        intercept_values.size != 1
        or not np.isfinite(intercept_values[0])
    ):
        raise ValueError(
            "Ridge 절편은 유한한 값 하나여야 합니다."
        )

    return artifacts


def save_model_artifacts(
    *,
    vectorizer: TfidfVectorizer,
    ridge_model: Ridge,
    model_name: str,
    model_variant: ModelVariant,
    model_version: int,
    tokenizer_version: str,
    dataset_start_date: date,
    dataset_end_date: date,
    output_path: str | Path,
) -> None:
    """
    선정된 text-only Ridge 모델과 재현 메타데이터를 저장한다.

    입력:
    - vectorizer: 전체 서비스 학습 Dataset으로 fit한 TF-IDF 객체다.
    - ridge_model: vectorizer의 TF-IDF 특성만으로 fit한 Ridge다.
    - model_name: DB artifacts와 bundle에서 공통으로 사용할 모델명이다.
    - model_variant: positive 또는 negative 수급 방향이다.
    - model_version: 같은 모델명의 서비스 모델 버전이다.
    - tokenizer_version: 일별문서와 모델의 토큰 계약 버전이다.
    - dataset_start_date, dataset_end_date: 최종 서비스 모델이 실제로
      fit한 전체 Dataset의 시작일과 종료일이다.
    - output_path: 생성할 신뢰된 로컬 .pkl 파일 경로다.

    출력:
    - 반환값은 없다. 부모 폴더를 만든 뒤 스키마 버전 2의 pickle
      bundle을 output_path에 저장한다.

    현재 선정 모델은 댓글 수 특성을 사용하지 않으므로 Scaler는 bundle에
    포함하지 않는다. 저장 전에 객체 종류와 계수 수를 모두 검증한다.
    """
    path = Path(output_path)

    if path.suffix.lower() != ".pkl":
        raise ValueError(
            "모델 산출물은 .pkl 형식으로 저장해야 합니다."
        )

    artifacts = {
        "artifact_schema_version": (
            MODEL_ARTIFACT_SCHEMA_VERSION
        ),
        "model_name": model_name.strip(),
        "model_variant": model_variant,
        "model_version": model_version,
        "feature_mode": "text_only",
        "tokenizer_version": tokenizer_version.strip(),
        "dataset_start_date": dataset_start_date,
        "dataset_end_date": dataset_end_date,
        "vectorizer": vectorizer,
        "ridge_model": ridge_model,
    }
    _validate_model_artifacts(artifacts)

    # 모델 파일을 저장할 상위 폴더가 없으면 생성한다.
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open("wb") as file:
        pickle.dump(
            artifacts,
            file,
            protocol=pickle.HIGHEST_PROTOCOL,
        )


def load_model_artifacts(
    model_path: str | Path,
) -> dict:
    """
    신뢰된 파일에서 text-only Ridge bundle을 복원하고 검증한다.

    입력:
    - model_path: 프로젝트가 직접 생성한 스키마 버전 2의 .pkl 경로다.

    출력:
    - 모델명·방향·버전·토크나이저·Dataset 기간과 학습된 vectorizer,
      ridge_model을 포함한 dict를 반환한다.

    pickle은 임의 코드를 실행할 수 있으므로 외부에서 받은 파일은 이
    함수에 전달하지 않는다. 기존 v1 Scaler 포함 bundle은 선정 모델
    계약과 다르므로 지원하지 않고 재학습 대상으로 처리한다.
    """
    path = Path(model_path)

    if path.suffix.lower() != ".pkl":
        raise ValueError(
            "모델 산출물은 .pkl 형식이어야 합니다."
        )

    # pickle은 Python 객체를 복원하므로
    # 프로젝트가 직접 생성한 신뢰할 수 있는 파일만 불러온다
    with path.open("rb") as file:
        artifacts = pickle.load(file)

    return _validate_model_artifacts(
        artifacts
    )


def resolve_registered_model_path(
    *,
    saved_path: str,
    base_dir: str | Path,
) -> Path:
    """DB의 저장소 상대 경로를 검증된 로컬 모델 경로로 바꾼다."""
    if not isinstance(saved_path, str) or not saved_path.strip():
        raise ValueError(
            "saved_path는 비어 있지 않은 문자열이어야 합니다."
        )

    relative_path = Path(saved_path.strip())

    if relative_path.is_absolute():
        raise ValueError(
            "DB 모델 경로는 저장소 기준 상대 경로여야 합니다."
        )

    base_path = Path(base_dir).resolve()
    model_path = (base_path / relative_path).resolve()

    try:
        model_path.relative_to(base_path)
    except ValueError as exc:
        raise ValueError(
            "DB 모델 경로가 프로젝트 저장소 밖을 가리킵니다."
        ) from exc

    return model_path


def load_registered_model_artifacts(
    *,
    model_name: str,
    model_variant: SupplyDirection,
    model_version: int,
    artifact_schema_version: int,
    base_dir: str | Path,
) -> tuple[dict, dict]:
    """DB에 등록된 모델 행과 검증된 로컬 bundle을 함께 불러온다."""
    artifact_record = select_model_artifact(
        model_name=model_name,
        model_variant=model_variant,
        model_version=model_version,
        artifact_schema_version=artifact_schema_version,
    )

    if artifact_record is None:
        raise FileNotFoundError(
            "DB에 등록된 모델 아티팩트가 없습니다: "
            f"model={model_name}, variant={model_variant}, "
            f"version={model_version}"
        )

    if artifact_record["scaler_name"] != "not_used":
        raise ValueError(
            "선정 text-only 모델의 scaler_name은 not_used여야 합니다."
        )

    model_path = resolve_registered_model_path(
        saved_path=artifact_record["saved_path"],
        base_dir=base_dir,
    )
    model_artifacts = load_model_artifacts(model_path)
    comparable_fields = (
        "artifact_schema_version",
        "model_name",
        "model_variant",
        "model_version",
        "tokenizer_version",
        "dataset_start_date",
        "dataset_end_date",
    )

    for field_name in comparable_fields:
        if artifact_record[field_name] != model_artifacts[field_name]:
            raise ValueError(
                "DB 아티팩트 정보와 모델 bundle이 다릅니다: "
                f"field={field_name}"
            )

    if model_artifacts["feature_mode"] != "text_only":
        raise ValueError(
            "추론 모델의 feature_mode가 text_only가 아닙니다."
        )

    if artifact_record["tokenizer_version"] != REQUIRED_TOKENIZER_VERSION:
        raise ValueError(
            "등록 모델의 tokenizer_version이 현재 서비스 토큰 계약과 다릅니다."
        )

    return artifact_record, model_artifacts
