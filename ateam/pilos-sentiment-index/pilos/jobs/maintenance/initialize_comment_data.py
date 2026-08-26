"""원본 파일 DB 등록 → 미적재분 전처리 순차 실행기.

register_raw_comment_files로 data/raw의 until_/from_ 파일을
source_comment_file에 등록한 뒤,
preprocess_comments 로 아직 DB 에 안 올라간 댓글을 전처리해
preprocessed_comment 에 적재한다. 둘 다 멱등이라 여러 번 실행해도 안전하다.

순서 중요: 전처리는 source_comment_file 에 등록된 파일만 처리하므로 등록이 먼저다.

실행: uv run python -m pilos.jobs.maintenance.initialize_comment_data
설정은 register_raw_comment_files의 상수를 사용한다.
"""
import logging
import sys

from pilos.collection.logging_setup import setup_logging
from pilos.jobs.preprocess_comments import run_pending_comment_preprocessing
from pilos.jobs.maintenance import register_raw_comment_files
from pilos.storage.comment_db import CommentDBUnavailableError

logger = logging.getLogger(__name__)


def main():
    """원본 파일을 DB에 등록한 뒤, 아직 적재 안 된 댓글을 전처리·적재한다(단계별 오류 격리)."""
    setup_logging()
    failures = []

    # 1) 원본 파일을 source_comment_file 에 등록(멱등, 이미 있으면 건너뜀).
    logger.info("[등록→전처리] 1/2 원본 파일 DB 등록")
    try:
        registered = register_raw_comment_files.input_to_db(
            register_raw_comment_files.INPUT_DIR,
            register_raw_comment_files.INPUT_PATTERNS,
        )
        logger.info(f"[등록→전처리] source 등록 {registered}건")
    except CommentDBUnavailableError:
        logger.error("[등록→전처리] DB 접속 실패로 원본 파일 등록을 시작하지 못함(DB 필수)")
        failures.append("register_raw_comment_files")
    except Exception:
        logger.exception("[등록→전처리] 원본 파일 DB 등록 실패")
        failures.append("register_raw_comment_files")

    # 2) 아직 DB 에 안 올라간 댓글 전처리·적재(from_+until_, watermark+INSERT IGNORE 로 멱등).
    #    초기 전체 적재이므로 until_ 백필 파일까지 포함한다(include_backfill=True).
    logger.info("[등록→전처리] 2/2 미적재분 전처리·적재")
    try:
        pre = run_pending_comment_preprocessing(include_backfill=True)
        logger.info(f"[등록→전처리] 전처리 적재 {pre.inserted}건 · 실패 {pre.failed}개")
        # 전 단계 예외가 아니라 파일 단위 부분 실패도 실패 단계로 집계(종료코드 1).
        if pre.failed:
            logger.error(f"[등록→전처리] 전처리 파일 부분 실패: {pre.failed_files}")
            failures.append("preprocess_partial")
    except Exception:
        logger.exception("[등록→전처리] 전처리·적재 실패")
        failures.append("preprocess")

    if failures:
        logger.error(f"[등록→전처리 종료] 실패 단계: {failures}")
        return 1
    logger.info("[등록→전처리 종료] 전체 성공")
    return 0


if __name__ == "__main__":
    sys.exit(main())
