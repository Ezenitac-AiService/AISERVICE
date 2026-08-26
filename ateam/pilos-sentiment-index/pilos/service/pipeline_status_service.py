"""Flask에 공개할 최신 파이프라인 상태를 구성한다."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pilos.storage.pipeline_run_db import (
    PipelineRunStorageError,
    select_latest_pipeline_run,
)


class PipelineStatusServiceError(RuntimeError):
    """최신 파이프라인 상태를 웹 응답으로 만들지 못한 경우."""


def _isoformat(value: date | datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _public_stage_summary(
    stages: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """내부 결과와 파일 경로를 제외하고 단계 상태와 소요시간만 공개한다."""
    public: dict[str, dict[str, Any]] = {}
    for stage_name, stage in stages.items():
        if not isinstance(stage, dict):
            continue
        public[str(stage_name)] = {
            "status": stage.get("status"),
            "elapsed_seconds": stage.get("elapsed_seconds"),
        }
    return public


def get_latest_pipeline_status_for_display() -> dict[str, Any]:
    """프론트가 polling할 수 있는 최신 실행 상태를 반환한다."""
    try:
        row = select_latest_pipeline_run()
    except PipelineRunStorageError as error:
        raise PipelineStatusServiceError(
            "파이프라인 상태를 조회할 수 없습니다."
        ) from error

    if row is None:
        return {"status": "not_started"}

    try:
        failed = row.get("status") == "failed"
        return {
            "service_pipeline_run_id": row["service_pipeline_run_id"],
            "status": row["status"],
            "target": row["target"],
            "tokenizer_version": row["tokenizer_version"],
            "operation_start_date": _isoformat(
                row["operation_start_date"]
            ),
            "started_at": _isoformat(row["started_at"]),
            "finished_at": _isoformat(row.get("finished_at")),
            "elapsed_seconds": row.get("elapsed_seconds"),
            "stopped_stage": row.get("stopped_stage"),
            "failure_type": row.get("failure_type") if failed else None,
            "failure_message": (
                "파이프라인 실행 중 오류가 발생했습니다."
                if failed
                else None
            ),
            "stages": _public_stage_summary(
                row.get("stage_summary", {})
            ),
        }
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise PipelineStatusServiceError(
            "저장된 파이프라인 상태 형식이 올바르지 않습니다."
        ) from error
