"""댓글 수집부터 v13 보고서 생성까지 서비스 운영 단계를 순차 실행한다.

Windows 작업 스케줄러는 이 모듈의 CLI를 배치 파일에서 시작한다. Python 내부에서는
각 단계의 CLI ``main``이나 subprocess를 호출하지 않고 기존 ``run_*`` 함수를 직접
호출하여 반환값과 예외로 다음 단계 진행 여부를 판단한다.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from time import monotonic
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


# 단계 모듈보다 먼저 루트 환경을 읽어 수집 솔트가 import 순서에 의존하지 않게 한다.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

from pilos.analysis.tokenizer_settings import TOKENIZER_VERSION
from pilos.jobs.build_daily_documents import run_daily_document_building
from pilos.jobs.collect_supply_demand import run_supply_demand_collection
from pilos.jobs.generate_llm_reports import run_pending_llm_report_generation
from pilos.jobs.incremental_comments import run_incremental
from pilos.jobs.predict_model import run_database_inference
from pilos.jobs.preprocess_comments import run_preprocessing_for_files
from pilos.jobs.tokenize_comments import run_pending_comment_tokenization
from pilos.model_config import SERVICE_INFERENCE_START_DATE
from pilos.storage.pipeline_run_db import (
    PipelineRunStorageError,
    finish_pipeline_run,
    start_pipeline_run,
)


logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"
DEFAULT_LOCK_PATH = (
    Path(tempfile.gettempdir())
    / "pilos-sentiment-index-service-pipeline.lock"
)


class PipelineAlreadyRunningError(RuntimeError):
    """동일 서비스 파이프라인의 이전 실행이 아직 진행 중인 상태."""


@dataclass(slots=True)
class PipelineRunSummary:
    """최상위 실행의 단계별 결과와 중단 사유."""

    status: str
    target: str
    tokenizer_version: str
    operation_start_date: date
    started_at: datetime
    service_pipeline_run_id: int | None = None
    finished_at: datetime | None = None
    elapsed_seconds: float = 0.0
    stopped_stage: str | None = None
    failure_type: str | None = None
    failure_message: str | None = None
    stages: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        return 0 if self.status == "completed" else 1

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(asdict(self))


def _to_jsonable(value: Any) -> Any:
    """실행기 반환 객체를 로그와 CLI JSON에 안전하게 담을 값으로 변환한다."""
    if is_dataclass(value) and not isinstance(value, type):
        return _to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


def _normalize_kst_now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(KST)
    if value.tzinfo is None:
        raise ValueError("now는 timezone 정보가 필요합니다.")
    return value.astimezone(KST)


def configure_pipeline_file_logging(
    *,
    log_dir: Path = DEFAULT_LOG_DIR,
    now: datetime | None = None,
) -> Path:
    """최상위 실행기가 수집한 요약만 기록하는 일별 로그를 구성한다."""
    kst_now = _normalize_kst_now(now)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / (
        f"service_pipeline_{kst_now.date().isoformat()}.log"
    )

    resolved_log_path = str(log_path.resolve())
    for handler in logger.handlers:
        if getattr(handler, "_pilos_pipeline_log_path", None) == (
            resolved_log_path
        ):
            return log_path

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s"
        )
    )
    setattr(
        file_handler,
        "_pilos_pipeline_log_path",
        resolved_log_path,
    )
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)
    return log_path


def _lock_file(file_handle: Any) -> None:
    file_handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)
        return

    import fcntl

    fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(file_handle: Any) -> None:
    file_handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def acquire_pipeline_lock(
    lock_path: Path = DEFAULT_LOCK_PATH,
) -> Iterator[None]:
    """프로세스 종료 시 자동 해제되는 비차단 파일 잠금을 획득한다."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as file_handle:
        if os.fstat(file_handle.fileno()).st_size == 0:
            file_handle.write(b"0")
            file_handle.flush()
        try:
            _lock_file(file_handle)
        except OSError as error:
            raise PipelineAlreadyRunningError(
                "이전 최상위 자동화 실행이 아직 진행 중입니다."
            ) from error

        try:
            yield
        finally:
            _unlock_file(file_handle)


def _stage_result(
    *,
    status: str,
    started_at: float,
    result: Any,
) -> dict[str, Any]:
    return {
        "status": status,
        "elapsed_seconds": round(monotonic() - started_at, 3),
        "result": _to_jsonable(result),
    }


def _inference_result_summary(
    results: dict[str, list[dict[str, Any]]],
    storage_summary: dict[str, int],
) -> dict[str, Any]:
    models: dict[str, dict[str, Any]] = {}
    for model_variant, rows in results.items():
        artifact_ids = sorted(
            {
                int(row["artifact_id"])
                for row in rows
                if row.get("artifact_id") is not None
            }
        )
        models[model_variant] = {
            "result_count": len(rows),
            "artifact_ids": artifact_ids,
        }
    return {
        "models": models,
        "storage": storage_summary,
    }


def _finish_summary(
    summary: PipelineRunSummary,
    *,
    started_monotonic: float,
    status: str,
    stopped_stage: str | None = None,
    error: Exception | None = None,
) -> PipelineRunSummary:
    summary.status = status
    summary.finished_at = datetime.now(KST)
    summary.elapsed_seconds = round(monotonic() - started_monotonic, 3)
    summary.stopped_stage = stopped_stage
    if error is not None:
        summary.failure_type = type(error).__name__
        summary.failure_message = str(error)
    return summary


def run_service_pipeline(
    *,
    target: str | None = None,
    now: datetime | None = None,
) -> PipelineRunSummary:
    """현재 DB 상태를 기준으로 서비스 운영 단계를 한 번 순차 실행한다.

    수집 일부 실패가 있어도 이미 기록된 파일의 전처리까지 수행한다. 수집 또는
    전처리에 실패가 남으면 토큰화부터는 시작하지 않는다. 이후 단계는 예외나 명시적인
    실패 수가 확인되면 다음 단계로 진행하지 않는다. 대상 0건과 수급 시간대 skip은
    정상 상태로 처리한다.
    """
    kst_now = _normalize_kst_now(now)
    started_monotonic = monotonic()
    target_label = target or "all"
    summary = PipelineRunSummary(
        status="running",
        target=target_label,
        tokenizer_version=TOKENIZER_VERSION,
        operation_start_date=SERVICE_INFERENCE_START_DATE,
        started_at=kst_now,
    )

    logger.info(
        "최상위 자동화 시작: target=%s, tokenizer_version=%s, date=%s",
        target_label,
        TOKENIZER_VERSION,
        kst_now.date(),
    )

    try:
        stage_started = monotonic()
        collection_summary = run_incremental(target=target)
        summary.stages["comment_collection"] = _stage_result(
            status=(
                "completed"
                if collection_summary.exit_code == 0
                else "partial_failure"
            ),
            started_at=stage_started,
            result=collection_summary,
        )

        stage_started = monotonic()
        preprocessing_summary = run_preprocessing_for_files(
            collection_summary.recorded_files
        )
        summary.stages["comment_preprocessing"] = _stage_result(
            status=(
                "completed"
                if preprocessing_summary.failed == 0
                else "partial_failure"
            ),
            started_at=stage_started,
            result=preprocessing_summary,
        )

        if collection_summary.exit_code != 0:
            error = RuntimeError(
                "댓글 수집 부분 실패가 있어 토큰화 이후 단계를 중단합니다."
            )
            return _finish_summary(
                summary,
                started_monotonic=started_monotonic,
                status="failed",
                stopped_stage="comment_collection",
                error=error,
            )
        if preprocessing_summary.failed > 0:
            error = RuntimeError(
                "댓글 전처리 부분 실패가 있어 토큰화 이후 단계를 중단합니다."
            )
            return _finish_summary(
                summary,
                started_monotonic=started_monotonic,
                status="failed",
                stopped_stage="comment_preprocessing",
                error=error,
            )

        stage_started = monotonic()
        tokenized_count = run_pending_comment_tokenization()
        summary.stages["comment_tokenization"] = _stage_result(
            status="completed",
            started_at=stage_started,
            result={
                "inserted_count": tokenized_count,
                "tokenizer_version": TOKENIZER_VERSION,
            },
        )

        stage_started = monotonic()
        daily_success_count, daily_failed_count = (
            run_daily_document_building()
        )
        summary.stages["daily_document"] = _stage_result(
            status=(
                "completed"
                if daily_failed_count == 0
                else "partial_failure"
            ),
            started_at=stage_started,
            result={
                "succeeded_count": daily_success_count,
                "failed_count": daily_failed_count,
            },
        )
        if daily_failed_count > 0:
            error = RuntimeError(
                "일별 문서 생성 부분 실패가 있어 후속 단계를 중단합니다."
            )
            return _finish_summary(
                summary,
                started_monotonic=started_monotonic,
                status="failed",
                stopped_stage="daily_document",
                error=error,
            )

        stage_started = monotonic()
        try:
            supply_result = run_supply_demand_collection(now=kst_now)
            summary.stages["supply_demand"] = _stage_result(
                status=str(supply_result.status.value),
                started_at=stage_started,
                result=supply_result,
            )
        except Exception as error:
            logger.warning(
                "수급 수집 단계 예외 발생(Graceful Fallback 처리): %s",
                error,
            )
            summary.stages["supply_demand"] = {
                "status": "skipped",
                "elapsed_seconds": round(monotonic() - stage_started, 3),
                "message": f"수급 수집 오류로 스킵: {error}",
            }

        stage_started = monotonic()
        inference_results, inference_storage_summary = (
            run_database_inference(
                inference_start_date=SERVICE_INFERENCE_START_DATE,
                inference_end_date=kst_now.date(),
            )
        )
        summary.stages["model_inference"] = _stage_result(
            status="completed",
            started_at=stage_started,
            result=_inference_result_summary(
                inference_results,
                inference_storage_summary,
            ),
        )

        stage_started = monotonic()
        report_summary = run_pending_llm_report_generation(
            report_start_date=SERVICE_INFERENCE_START_DATE,
            report_end_date=kst_now.date(),
        )
        report_failed_count = int(report_summary.get("failed_count", 0))
        summary.stages["llm_report"] = _stage_result(
            status=(
                "completed"
                if report_failed_count == 0
                else "partial_failure"
            ),
            started_at=stage_started,
            result=report_summary,
        )
        if report_failed_count > 0:
            logger.warning("LLM 보고서 일부 대상 미완료/대기(failed_count=%d), 다음 주기에 재시도합니다.", report_failed_count)

    except Exception as error:
        stopped_stage = next(
            (
                stage
                for stage in (
                    "comment_collection",
                    "comment_preprocessing",
                    "comment_tokenization",
                    "daily_document",
                    "supply_demand",
                    "model_inference",
                    "llm_report",
                )
                if stage not in summary.stages
            ),
            "unknown",
        )
        logger.error(
            "최상위 자동화 실패: stage=%s, error_type=%s, error=%s",
            stopped_stage,
            type(error).__name__,
            error,
        )
        return _finish_summary(
            summary,
            started_monotonic=started_monotonic,
            status="failed",
            stopped_stage=stopped_stage,
            error=error,
        )

    return _finish_summary(
        summary,
        started_monotonic=started_monotonic,
        status="completed",
    )


def run_tracked_service_pipeline(
    *,
    target: str | None = None,
    now: datetime | None = None,
) -> PipelineRunSummary:
    """DB에 시작·종료 상태를 남기며 서비스 파이프라인을 한 번 실행한다."""
    kst_now = _normalize_kst_now(now)
    started_monotonic = monotonic()
    target_label = target or "all"

    try:
        pipeline_run_id = start_pipeline_run(
            target=target_label,
            tokenizer_version=TOKENIZER_VERSION,
            operation_start_date=SERVICE_INFERENCE_START_DATE,
            started_at=kst_now,
        )
    except PipelineRunStorageError as error:
        logger.error("파이프라인 시작 상태 저장 실패: %s", error)
        summary = PipelineRunSummary(
            status="running",
            target=target_label,
            tokenizer_version=TOKENIZER_VERSION,
            operation_start_date=SERVICE_INFERENCE_START_DATE,
            started_at=kst_now,
        )
        return _finish_summary(
            summary,
            started_monotonic=started_monotonic,
            status="failed",
            stopped_stage="pipeline_status_start",
            error=error,
        )

    summary = run_service_pipeline(target=target, now=kst_now)
    summary.service_pipeline_run_id = pipeline_run_id
    try:
        finish_pipeline_run(
            service_pipeline_run_id=pipeline_run_id,
            summary=asdict(summary),
        )
    except PipelineRunStorageError as error:
        logger.error("파이프라인 종료 상태 저장 실패: %s", error)
        summary.stages["pipeline_status"] = {
            "status": "failed",
            "elapsed_seconds": 0.0,
            "result": {
                "failure_type": type(error).__name__,
                "failure_message": str(error),
            },
        }
        if summary.status == "completed":
            return _finish_summary(
                summary,
                started_monotonic=started_monotonic,
                status="failed",
                stopped_stage="pipeline_status_finish",
                error=error,
            )

    return summary


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "댓글 증분 수집부터 v13 LLM 보고서 생성까지 "
            "서비스 운영 단계를 한 번 실행합니다."
        )
    )
    parser.add_argument(
        "--target",
        choices=("all", "sk", "others"),
        default="all",
        help="댓글 수집 대상. 기본값은 전체 종목입니다.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        ),
    )
    log_path = configure_pipeline_file_logging()
    logger.info("최상위 자동화 로그 파일: %s", log_path)

    try:
        with acquire_pipeline_lock():
            summary = run_tracked_service_pipeline(
                target=(
                    None
                    if arguments.target == "all"
                    else arguments.target
                )
            )
    except PipelineAlreadyRunningError as error:
        logger.error("최상위 자동화 중복 실행 차단: %s", error)
        return 1

    summary_json = json.dumps(
        summary.to_dict(),
        ensure_ascii=False,
        indent=2,
    )
    logger.info("최상위 자동화 최종 요약:\n%s", summary_json)
    print(summary_json)
    return summary.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
