"""최상위 서비스 파이프라인 실행 상태의 MySQL 입출력을 담당한다."""

from __future__ import annotations

import json

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from pilos.storage.db import get_engine


KST = ZoneInfo("Asia/Seoul")


class PipelineRunStorageError(RuntimeError):
    """파이프라인 실행 상태를 저장하거나 조회하지 못한 경우."""


_INSERT_PIPELINE_RUN = text(
    """
    INSERT INTO service_pipeline_run (
        status,
        target,
        tokenizer_version,
        operation_start_date,
        started_at,
        stage_summary
    ) VALUES (
        'running',
        :target,
        :tokenizer_version,
        :operation_start_date,
        :started_at,
        :stage_summary
    )
    """
)


_UPDATE_PIPELINE_RUN = text(
    """
    UPDATE service_pipeline_run
    SET
        status = :status,
        finished_at = :finished_at,
        elapsed_seconds = :elapsed_seconds,
        stopped_stage = :stopped_stage,
        failure_type = :failure_type,
        failure_message = :failure_message,
        stage_summary = :stage_summary,
        updated_at = CURRENT_TIMESTAMP(6)
    WHERE service_pipeline_run_id = :service_pipeline_run_id
      AND status = 'running'
    """
)


_SELECT_LATEST_PIPELINE_RUN = text(
    """
    SELECT
        service_pipeline_run_id,
        status,
        target,
        tokenizer_version,
        operation_start_date,
        started_at,
        finished_at,
        elapsed_seconds,
        stopped_stage,
        failure_type,
        failure_message,
        stage_summary
    FROM service_pipeline_run
    ORDER BY started_at DESC, service_pipeline_run_id DESC
    LIMIT 1
    """
)


def _to_db_kst(value: datetime) -> datetime:
    """timezone-aware 시각을 DB 표준인 timezone 없는 KST로 변환한다."""
    if value.tzinfo is None:
        return value
    return value.astimezone(KST).replace(tzinfo=None)


def _serialize_stage_summary(stages: dict[str, Any]) -> str:
    return json.dumps(
        stages,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def start_pipeline_run(
    *,
    target: str,
    tokenizer_version: str,
    operation_start_date: date,
    started_at: datetime,
) -> int:
    """파이프라인 시작 상태를 신규 행으로 기록하고 실행 ID를 반환한다."""
    try:
        engine = get_engine()
        with engine.begin() as connection:
            result = connection.execute(
                _INSERT_PIPELINE_RUN,
                {
                    "target": target,
                    "tokenizer_version": tokenizer_version,
                    "operation_start_date": operation_start_date,
                    "started_at": _to_db_kst(started_at),
                    "stage_summary": _serialize_stage_summary({}),
                },
            )
        return int(result.lastrowid)
    except (SQLAlchemyError, RuntimeError, TypeError, ValueError) as error:
        raise PipelineRunStorageError(
            "파이프라인 시작 상태를 저장하지 못했습니다."
        ) from error


def finish_pipeline_run(
    *,
    service_pipeline_run_id: int,
    summary: dict[str, Any],
) -> None:
    """실행 중인 동일 행을 최종 성공 또는 실패 상태로 마감한다."""
    status = summary.get("status")
    if status not in {"completed", "failed"}:
        raise ValueError("최종 파이프라인 상태는 completed 또는 failed여야 합니다.")

    finished_at = summary.get("finished_at")
    if not isinstance(finished_at, datetime):
        raise ValueError("파이프라인 종료 시각이 필요합니다.")

    try:
        engine = get_engine()
        with engine.begin() as connection:
            result = connection.execute(
                _UPDATE_PIPELINE_RUN,
                {
                    "service_pipeline_run_id": service_pipeline_run_id,
                    "status": status,
                    "finished_at": _to_db_kst(finished_at),
                    "elapsed_seconds": summary.get("elapsed_seconds"),
                    "stopped_stage": summary.get("stopped_stage"),
                    "failure_type": summary.get("failure_type"),
                    "failure_message": summary.get("failure_message"),
                    "stage_summary": _serialize_stage_summary(
                        summary.get("stages", {})
                    ),
                },
            )
        if result.rowcount != 1:
            raise PipelineRunStorageError(
                "실행 중인 파이프라인 상태 행을 찾지 못했습니다."
            )
    except PipelineRunStorageError:
        raise
    except (SQLAlchemyError, RuntimeError, TypeError, ValueError) as error:
        raise PipelineRunStorageError(
            "파이프라인 종료 상태를 저장하지 못했습니다."
        ) from error


def _deserialize_stage_summary(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("stage_summary가 JSON 객체가 아닙니다.")


def select_latest_pipeline_run() -> dict[str, Any] | None:
    """가장 최근에 시작된 파이프라인 실행 상태를 조회한다."""
    try:
        engine = get_engine()
        with engine.connect() as connection:
            row = connection.execute(
                _SELECT_LATEST_PIPELINE_RUN
            ).mappings().first()
        if row is None:
            return None

        result = dict(row)
        result["stage_summary"] = _deserialize_stage_summary(
            result.get("stage_summary")
        )
        elapsed_seconds = result.get("elapsed_seconds")
        if isinstance(elapsed_seconds, Decimal):
            result["elapsed_seconds"] = float(elapsed_seconds)
        return result
    except (
        SQLAlchemyError,
        RuntimeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        raise PipelineRunStorageError(
            "최신 파이프라인 상태를 조회하지 못했습니다."
        ) from error
