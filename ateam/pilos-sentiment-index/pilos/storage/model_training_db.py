from datetime import date
from typing import Literal

from sqlalchemy import bindparam, text

from pilos.storage.db import get_engine


SupplyDirection = Literal[
    "positive",
    "negative",
]


def _validate_model_artifact_identity(
    *,
    model_name: str,
    model_variant: SupplyDirection,
    model_version: int,
) -> tuple[str, SupplyDirection, int]:
    """
    DB에서 모델 아티팩트를 식별할 세 값을 검증하고 정규화한다.

    입력:
    - model_name: 서비스 모델의 공통 이름이다.
    - model_variant: positive 또는 negative 방향이다.
    - model_version: 같은 이름·방향 안에서 사용할 1 이상의 버전이다.

    출력:
    - 앞뒤 공백을 제거한 model_name, 검증된 model_variant와
      model_version을 같은 순서로 반환한다.
    """
    model_name = model_name.strip()

    if not model_name:
        raise ValueError(
            "model_name은 비어 있을 수 없습니다."
        )

    if model_variant not in {
        "positive",
        "negative",
    }:
        raise ValueError(
            "model_variant는 positive 또는 negative여야 합니다."
        )

    if (
        not isinstance(model_version, int)
        or isinstance(model_version, bool)
        or model_version <= 0
    ):
        raise ValueError(
            "model_version은 1 이상의 정수여야 합니다."
        )

    return (
        model_name,
        model_variant,
        model_version,
    )


def select_model_training_records(
    *,
    tokenizer_version: str,
    training_end_date: date,
    supply_direction: SupplyDirection,
) -> list[dict]:
    """
    지정한 수급 방향과 학습 종료일에 해당하는
    종목별 최신 일별 문서와 수급지수를 함께 조회한다.
    """
    tokenizer_version = tokenizer_version.strip()

    if not tokenizer_version:
        raise ValueError(
            "tokenizer_version은 비어 있을 수 없습니다."
        )

    if supply_direction not in {
        "positive",
        "negative",
    }:
        raise ValueError(
            "supply_direction은 positive 또는 negative여야 합니다."
        )

    sql = text("""
        SELECT
            dd.daily_document_id,
            s.stock_code,
            dd.model_date,
            dd.tfidf_text,
            dd.comment_count,
            sd.supply_demand_index
        FROM daily_document AS dd
        INNER JOIN stock AS s
            ON s.stock_id = dd.stock_id
        INNER JOIN supply_demand AS sd
            ON sd.stock_id = dd.stock_id
           AND sd.trade_date = dd.model_date
        WHERE dd.tokenizer_version = :tokenizer_version
          AND dd.model_date <= :training_end_date
          AND sd.data_status = 'confirmed'
          AND (
                (
                    :supply_direction = 'positive'
                    AND sd.supply_demand_index > 0
                )
                OR
                (
                    :supply_direction = 'negative'
                    AND sd.supply_demand_index < 0
                )
              )
          AND NOT EXISTS (
              SELECT 1
              FROM daily_document AS newer_dd
              WHERE newer_dd.stock_id = dd.stock_id
                AND newer_dd.model_date = dd.model_date
                AND newer_dd.tokenizer_version
                    = dd.tokenizer_version
                AND newer_dd.daily_document_id
                    > dd.daily_document_id
          )
        ORDER BY
            dd.model_date ASC,
            dd.stock_id ASC
    """)

    engine = get_engine()

    with engine.connect() as conn:
        result = conn.execute(
            sql,
            {
                "tokenizer_version": tokenizer_version,
                "training_end_date": training_end_date,
                "supply_direction": supply_direction,
            },
        )

        return [
            dict(row)
            for row in result.mappings()
        ]


def select_daily_document_stock_metadata(
    *,
    daily_document_ids: list[int],
) -> dict[int, dict]:
    """학습 Dataset 문서의 stock_id와 표시용 종목명을 읽는다."""
    if not daily_document_ids:
        return {}

    normalized_ids = []

    for daily_document_id in daily_document_ids:
        if (
            not isinstance(daily_document_id, int)
            or isinstance(daily_document_id, bool)
            or daily_document_id <= 0
        ):
            raise ValueError("daily_document_id는 1 이상의 정수여야 합니다.")

        normalized_ids.append(daily_document_id)

    sql = text("""
        SELECT
            dd.daily_document_id,
            dd.stock_id,
            s.stock_code,
            s.stock_name
        FROM daily_document AS dd
        INNER JOIN stock AS s
            ON s.stock_id = dd.stock_id
        WHERE dd.daily_document_id IN :daily_document_ids
    """).bindparams(
        bindparam("daily_document_ids", expanding=True)
    )

    with get_engine().connect() as conn:
        rows = conn.execute(
            sql,
            {"daily_document_ids": sorted(set(normalized_ids))},
        ).mappings()
        return {
            int(row["daily_document_id"]): dict(row)
            for row in rows
        }


def select_model_artifact(
    *,
    model_name: str,
    model_variant: SupplyDirection,
    model_version: int,
    artifact_schema_version: int,
) -> dict | None:
    """
    정확한 모델 식별자와 스키마 버전으로 아티팩트 정보를 조회한다.

    입력:
    - model_name, model_variant, model_version: 학습 실행기와 추론
      실행기가 공유하는 모델 식별자다.
    - artifact_schema_version: 로더가 지원하는 bundle 계약 버전이다.

    출력:
    - 일치하는 행이 없으면 None을 반환한다.
    - 한 행이면 artifact_id, saved_path, 모델·토크나이저 버전, Dataset
      기간과 저장 당시 평가 지표를 포함한 dict를 반환한다.

    같은 모델 식별자가 두 행 이상이면 어떤 파일을 사용해야 하는지
    결정할 수 없으므로 최신 행을 임의 선택하지 않고 오류를 발생시킨다.
    """
    (
        model_name,
        model_variant,
        model_version,
    ) = _validate_model_artifact_identity(
        model_name=model_name,
        model_variant=model_variant,
        model_version=model_version,
    )

    if (
        not isinstance(artifact_schema_version, int)
        or isinstance(artifact_schema_version, bool)
        or artifact_schema_version <= 0
    ):
        raise ValueError(
            "artifact_schema_version은 1 이상의 정수여야 합니다."
        )

    sql = text("""
        SELECT
            artifact_id,
            artifact_type,
            saved_path,
            artifact_schema_version,
            model_name,
            model_variant,
            model_version,
            vectorizer_name,
            scaler_name,
            tokenizer_version,
            dataset_start_date,
            dataset_end_date,
            validation_start_date,
            train_record_count,
            validation_record_count,
            train_mae,
            train_rmse,
            train_r2,
            validation_mae,
            validation_rmse,
            validation_r2
        FROM artifacts
        WHERE model_name = :model_name
          AND model_variant = :model_variant
          AND model_version = :model_version
          AND artifact_schema_version
              = :artifact_schema_version
        ORDER BY artifact_id DESC
        LIMIT 2
    """)
    engine = get_engine()

    with engine.connect() as conn:
        rows = [
            dict(row)
            for row in conn.execute(
                sql,
                {
                    "model_name": model_name,
                    "model_variant": model_variant,
                    "model_version": model_version,
                    "artifact_schema_version": (
                        artifact_schema_version
                    ),
                },
            ).mappings()
        ]

    if len(rows) > 1:
        raise RuntimeError(
            "같은 모델 식별자와 스키마 버전의 "
            "아티팩트가 두 개 이상 존재합니다."
        )

    return rows[0] if rows else None


def insert_model_artifact(
    *,
    artifact_data: dict,
) -> int:
    """학습된 모델 아티팩트의 정보와 성능 지표를 저장한다."""
    required_fields = {
        "artifact_type",
        "saved_path",
        "artifact_schema_version",
        "model_name",
        "model_variant",
        "model_version",
        "vectorizer_name",
        "scaler_name",
        "tokenizer_version",
        "dataset_start_date",
        "dataset_end_date",
        "validation_start_date",
        "train_record_count",
        "validation_record_count",
        "train_mae",
        "train_rmse",
        "train_r2",
        "validation_mae",
        "validation_rmse",
        "validation_r2",
    }

    missing_fields = (
        required_fields - artifact_data.keys()
    )

    if missing_fields:
        raise ValueError(
            "아티팩트 적재에 필요한 필드가 없습니다: "
            f"{sorted(missing_fields)}"
        )

    unexpected_fields = (
        artifact_data.keys() - required_fields
    )

    if unexpected_fields:
        raise ValueError(
            "아티팩트 적재 계약에 없는 필드가 있습니다: "
            f"{sorted(unexpected_fields)}"
        )

    if artifact_data["model_variant"] not in {
        "positive",
        "negative",
    }:
        raise ValueError(
            "model_variant는 positive 또는 negative여야 합니다."
        )

    (
        artifact_data["model_name"],
        artifact_data["model_variant"],
        artifact_data["model_version"],
    ) = _validate_model_artifact_identity(
        model_name=artifact_data["model_name"],
        model_variant=artifact_data["model_variant"],
        model_version=artifact_data["model_version"],
    )

    if (
        artifact_data["dataset_start_date"]
        > artifact_data["dataset_end_date"]
    ):
        raise ValueError(
            "Dataset 시작일은 종료일보다 늦을 수 없습니다."
        )

    duplicate_sql = text("""
        SELECT artifact_id
        FROM artifacts
        WHERE model_name = :model_name
          AND model_variant = :model_variant
          AND model_version = :model_version
        LIMIT 1
    """)
    insert_sql = text("""
        INSERT INTO artifacts (
            artifact_type,
            saved_path,
            artifact_schema_version,
            model_name,
            model_variant,
            model_version,
            vectorizer_name,
            scaler_name,
            tokenizer_version,
            dataset_start_date,
            dataset_end_date,
            validation_start_date,
            train_record_count,
            validation_record_count,
            train_mae,
            train_rmse,
            train_r2,
            validation_mae,
            validation_rmse,
            validation_r2
        )
        VALUES (
            :artifact_type,
            :saved_path,
            :artifact_schema_version,
            :model_name,
            :model_variant,
            :model_version,
            :vectorizer_name,
            :scaler_name,
            :tokenizer_version,
            :dataset_start_date,
            :dataset_end_date,
            :validation_start_date,
            :train_record_count,
            :validation_record_count,
            :train_mae,
            :train_rmse,
            :train_r2,
            :validation_mae,
            :validation_rmse,
            :validation_r2
        )
    """)

    engine = get_engine()

    with engine.begin() as conn:
        duplicate_artifact_id = conn.execute(
            duplicate_sql,
            {
                "model_name": artifact_data[
                    "model_name"
                ],
                "model_variant": artifact_data[
                    "model_variant"
                ],
                "model_version": artifact_data[
                    "model_version"
                ],
            },
        ).scalar_one_or_none()

        if duplicate_artifact_id is not None:
            raise ValueError(
                "같은 모델명·방향·버전의 아티팩트가 "
                "이미 DB에 존재합니다: "
                f"artifact_id={duplicate_artifact_id}"
            )

        result = conn.execute(
            insert_sql,
            artifact_data,
        )

        artifact_id = result.lastrowid

        if artifact_id is None:
            raise RuntimeError(
                "적재된 아티팩트 ID를 확인할 수 없습니다."
            )

    return int(artifact_id)
