"""원본 댓글 파일을 전처리하고 DB에 적재하는 실행기."""

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from pilos.analysis.preprocessor import (
    preprocess_comments,
    records_to_comment_dataframe,
)
from pilos.storage.jsonl import iter_jsonl_records
from pilos.storage.normalization import normalize_comment_dataframe
from pilos.storage.preprocess_db import (
    insert_preprocessed_comments,
    select_source_file_by_name,
    select_source_files_with_watermark,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


@dataclass
class PreprocessRunSummary:
    """전처리 실행 한 회의 파일 단위 처리 결과다."""

    total: int = 0
    inserted: int = 0
    failed: int = 0
    failed_files: list[str] = field(default_factory=list)


def _build_input_path(source_file: dict) -> Path:
    return (
        DATA_DIR
        / source_file["file_path"]
        / f'{source_file["file_name"]}.{source_file["file_ext"]}'
    )


def run_comment_preprocessing(
    input_path: str | Path,
    start_after_line: int = 0,
) -> pd.DataFrame:
    """원본 파일 하나의 watermark 이후 행을 정규화·전처리한다."""

    records = iter_jsonl_records(
        input_path,
        start_after_line=start_after_line,
    )
    comment_df = records_to_comment_dataframe(records)
    comment_df = normalize_comment_dataframe(comment_df)
    return preprocess_comments(comment_df)


def preprocess_one_source_file(source_file: dict) -> int:
    """원본 파일 하나의 새 줄만 전처리·적재한다."""

    source_file_name = source_file["file_name"]
    processed_line = source_file.get("processed_line") or 0
    input_path = _build_input_path(source_file)

    logger.info(
        "파일 처리 시작: source_file_name=%s, path=%s, watermark=%d",
        source_file_name,
        input_path,
        processed_line,
    )
    processed_df = run_comment_preprocessing(
        input_path,
        start_after_line=processed_line,
    )
    if processed_df.empty:
        logger.info("새 줄 없음 - 건너뜀: source_file_name=%s", source_file_name)
        return 0

    processed_df["stock_id"] = source_file["stock_id"]
    processed_df["source_comment_file_id"] = source_file[
        "source_comment_file_id"
    ]
    inserted_count = insert_preprocessed_comments(processed_df)
    logger.info(
        "전처리 결과 적재 완료: source_file_name=%s, count=%d",
        source_file_name,
        inserted_count,
    )
    return inserted_count


def _preprocess_source_files(source_files: list[dict]) -> PreprocessRunSummary:
    summary = PreprocessRunSummary(total=len(source_files))
    for source_file in source_files:
        try:
            summary.inserted += preprocess_one_source_file(source_file)
        except Exception:
            file_name = str(source_file.get("file_name"))
            summary.failed += 1
            summary.failed_files.append(file_name)
            logger.exception(
                "파일 처리 실패: source_file_name=%s",
                file_name,
            )
    return summary


def run_preprocessing_for_files(recorded_files) -> PreprocessRunSummary:
    """수집 실행이 기록한 파일만 watermark 이후 전처리·적재한다."""

    file_names = list(
        dict.fromkeys(
            Path(path).name.rsplit(".", maxsplit=1)[0]
            for path in recorded_files
        )
    )
    source_files: list[dict] = []
    missing_files: list[str] = []
    for file_name in file_names:
        source_file = select_source_file_by_name(file_name)
        if source_file is None:
            missing_files.append(file_name)
            logger.warning(
                "source_comment_file 미등록 - 전처리 건너뜀: file_name=%s",
                file_name,
            )
            continue
        source_files.append(source_file)

    summary = _preprocess_source_files(source_files)
    summary.total = len(file_names)
    summary.failed += len(missing_files)
    summary.failed_files = missing_files + summary.failed_files
    logger.info(
        "[증분 파일 전처리] 대상 %d · 적재 %d · 실패 %d%s",
        summary.total,
        summary.inserted,
        summary.failed,
        f" ({summary.failed_files})" if summary.failed_files else "",
    )
    return summary


def run_pending_comment_preprocessing(
    include_backfill: bool = False,
) -> PreprocessRunSummary:
    """DB에 등록된 원본 파일의 watermark 이후 새 줄을 처리한다."""

    source_files = select_source_files_with_watermark(
        target_date=None,
        include_backfill=include_backfill,
    )
    logger.info(
        "전처리 대상 파일 수: %d개 (include_backfill=%s)",
        len(source_files),
        include_backfill,
    )
    return _preprocess_source_files(source_files)


def main(include_backfill: bool = False) -> int:
    summary = run_pending_comment_preprocessing(
        include_backfill=include_backfill,
    )
    logger.info(
        "전체 전처리 완료: 적재 %d건, 대상 %d개, 실패 %d개%s",
        summary.inserted,
        summary.total,
        summary.failed,
        f" ({summary.failed_files})" if summary.failed_files else "",
    )
    return 1 if summary.failed else 0


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m pilos.jobs.preprocess_comments",
        description=(
            "미적재 원본 댓글을 전처리해 preprocessed_comment에 적재합니다."
        ),
    )
    parser.add_argument(
        "--include-backfill",
        action="store_true",
        help="until_ 백필 파일도 포함합니다.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        ),
    )
    args = _parse_args()
    sys.exit(main(include_backfill=args.include_backfill))
