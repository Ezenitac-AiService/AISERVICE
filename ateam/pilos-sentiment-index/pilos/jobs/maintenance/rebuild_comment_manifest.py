"""매니페스트 초기화 실행기: 기존 수집 파일을 스캔해 종목별 매니페스트를 재작성한다.

manifest 도입 이전에 모은 백필/증분 자료(until_*, from_*)를 커버리지·일별 카운트에
반영한다. 파일을 진실원본으로 절대값을 덮어쓰므로 여러 번 실행해도 안전(멱등)하다.

실행: uv run python -m pilos.jobs.maintenance.rebuild_comment_manifest
"""
import logging
import sys

from pilos.collection.constants import STOCK_NAME, SUBJECTID_WHITE_LIST
from pilos.collection.logging_setup import setup_logging
from pilos.storage import manifest
from pilos.storage.json_io import get_data_dir

logger = logging.getLogger(__name__)

# 초기화 대상. 기본 전체 종목.
TARGETS = SUBJECTID_WHITE_LIST


def _rebuild_one(subject_id):
    """한 종목의 모든 수집 파일을 스캔해 매니페스트를 재작성하고 총 건수를 반환한다."""
    name = STOCK_NAME[subject_id]
    data_dir = get_data_dir()
    until_files = sorted(data_dir.glob(f"until_*_{name}_comment.jsonl"))
    from_files = sorted(data_dir.glob(f"from_*_{name}_comment.jsonl"))

    # 일별 총 댓글 수(until+from) + from_ 기준 recent_id 를 공통 함수가 파일 스캔으로 채운다.
    # (기존 modes.backfill 은 manifest.rebuild 가 로드·병합하므로 그대로 보존된다.)
    m = manifest.rebuild_from_files(name, subject_id)
    total = sum((m.get("daily_counts") or {}).values())
    logger.info(f"[{name}] 재작성: 파일 {len(until_files) + len(from_files)}개 "
                f"(until {len(until_files)}, from {len(from_files)}) · 총 {total}건 · 커버리지 {m.get('coverage')}")
    return total


def main():
    """대상 종목의 매니페스트를 파일 스캔으로 재작성한다(종목별 오류는 격리)."""
    setup_logging()
    logger.info(f"[매니페스트 초기화 시작] 대상 {len(TARGETS)}종목")
    failures = []
    for subject_id in TARGETS:
        name = STOCK_NAME[subject_id]
        try:
            _rebuild_one(subject_id)
        except Exception:
            logger.exception(f"{name}({subject_id}) 매니페스트 초기화 실패 - 다음 종목")
            failures.append(name)
    if failures:
        logger.error(f"[매니페스트 초기화 종료] 실패 {len(failures)}: {failures}")
        return 1
    logger.info(f"[매니페스트 초기화 종료] 성공 {len(TARGETS)}/{len(TARGETS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
