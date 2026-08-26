"""Flask 사용 사례가 공유하는 활성 서비스 모델 identity와 로드 캐시."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from pilos.analysis.tokenizer import create_current_kiwi
from pilos.model_config import (
    ACTIVE_SERVICE_MODEL_VERSION,
    REQUIRED_TOKENIZER_VERSION,
    SERVICE_MODEL_ARTIFACT_SCHEMA_VERSION,
    SERVICE_MODEL_NAME,
    SERVICE_MODEL_VARIANTS,
)
from pilos.storage.model_artifacts import load_registered_model_artifacts
from pilos.storage.model_training_db import select_model_artifact


BASE_DIR = Path(__file__).resolve().parents[2]


class ActiveServiceModelError(RuntimeError):
    """현재 서비스용 두 방향 모델을 함께 준비할 수 없는 상태."""


@dataclass(frozen=True, slots=True)
class ActiveServiceModelContext:
    """검증된 활성 Positive·Negative bundle과 식별자 묶음."""

    positive_artifact_id: int
    negative_artifact_id: int
    tokenizer_version: str
    cache_identity: tuple[object, ...]
    positive_model_artifacts: dict[str, Any]
    negative_model_artifacts: dict[str, Any]


def _artifact_identity(record: dict[str, Any]) -> tuple[object, ...]:
    return (
        int(record["artifact_id"]),
        str(record["saved_path"]),
        str(record["model_name"]),
        str(record["model_variant"]),
        int(record["model_version"]),
        int(record["artifact_schema_version"]),
        str(record["tokenizer_version"]),
        record["dataset_start_date"],
        record["dataset_end_date"],
    )


def _select_active_records() -> tuple[dict[str, Any], dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    try:
        for model_variant in SERVICE_MODEL_VARIANTS:
            record = select_model_artifact(
                model_name=SERVICE_MODEL_NAME,
                model_variant=model_variant,
                model_version=ACTIVE_SERVICE_MODEL_VERSION,
                artifact_schema_version=SERVICE_MODEL_ARTIFACT_SCHEMA_VERSION,
            )
            if record is None:
                raise ActiveServiceModelError(
                    f"활성 {model_variant} 모델 artifact가 없습니다."
                )
            if record["tokenizer_version"] != REQUIRED_TOKENIZER_VERSION:
                raise ActiveServiceModelError(
                    "활성 모델의 tokenizer_version이 현재 서비스 계약과 다릅니다."
                )
            records[model_variant] = record
    except ActiveServiceModelError:
        raise
    except Exception as exc:
        raise ActiveServiceModelError(
            "활성 서비스 모델 정보를 조회할 수 없습니다."
        ) from exc

    return records["positive"], records["negative"]


@lru_cache(maxsize=8)
def _load_context(
    positive_identity: tuple[object, ...],
    negative_identity: tuple[object, ...],
) -> ActiveServiceModelContext:
    """DB record identity가 달라질 때만 bundle을 새로 로드한다."""
    try:
        positive_record, positive_bundle = load_registered_model_artifacts(
            model_name=SERVICE_MODEL_NAME,
            model_variant="positive",
            model_version=ACTIVE_SERVICE_MODEL_VERSION,
            artifact_schema_version=SERVICE_MODEL_ARTIFACT_SCHEMA_VERSION,
            base_dir=BASE_DIR,
        )
        negative_record, negative_bundle = load_registered_model_artifacts(
            model_name=SERVICE_MODEL_NAME,
            model_variant="negative",
            model_version=ACTIVE_SERVICE_MODEL_VERSION,
            artifact_schema_version=SERVICE_MODEL_ARTIFACT_SCHEMA_VERSION,
            base_dir=BASE_DIR,
        )
    except Exception as exc:
        raise ActiveServiceModelError(
            "활성 서비스 모델 bundle을 준비할 수 없습니다."
        ) from exc

    if _artifact_identity(positive_record) != positive_identity:
        raise ActiveServiceModelError(
            "Positive 모델 artifact identity가 조회 시점과 다릅니다."
        )
    if _artifact_identity(negative_record) != negative_identity:
        raise ActiveServiceModelError(
            "Negative 모델 artifact identity가 조회 시점과 다릅니다."
        )

    cache_identity = positive_identity + negative_identity
    return ActiveServiceModelContext(
        positive_artifact_id=int(positive_record["artifact_id"]),
        negative_artifact_id=int(negative_record["artifact_id"]),
        tokenizer_version=str(positive_record["tokenizer_version"]),
        cache_identity=cache_identity,
        positive_model_artifacts=positive_bundle,
        negative_model_artifacts=negative_bundle,
    )


def get_active_service_model_context() -> ActiveServiceModelContext:
    """현재 DB identity에 맞는 bundle cache를 반환한다.

    DB metadata는 요청마다 다시 확인한다. 따라서 활성 artifact가 바뀌면
    이전 bundle cache key를 재사용하지 않는다.
    """
    positive_record, negative_record = _select_active_records()
    return _load_context(
        _artifact_identity(positive_record),
        _artifact_identity(negative_record),
    )


@lru_cache(maxsize=8)
def _load_tokenizer(cache_identity: tuple[object, ...]) -> Any:
    """모델 identity별 Kiwi 한 개를 지연 생성한다."""
    del cache_identity
    return create_current_kiwi()


def get_active_service_tokenizer(
    context: ActiveServiceModelContext,
) -> Any:
    return _load_tokenizer(context.cache_identity)
