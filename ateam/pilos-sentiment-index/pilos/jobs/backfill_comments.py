"""백필 실행기: 지정 종목을 최신부터 하한 날짜까지 과거로 수집한다.

명령행 인자로 하한 날짜와 대상 종목을 지정한다.
실행 예:
  uv run python -m pilos.jobs.backfill_comments --target sk
  uv run python -m pilos.jobs.backfill_comments --target others --until-date 2026-04-30
"""
import argparse
import logging
import sys
from datetime import datetime

from pilos.collection.comment_crawler import crawl_until_date
from pilos.collection.constants import (
    KST,
    RESUME_UNTIL_DATE,
    SK_HYNIX_ID,
)
from pilos.collection.data_masking import (
    MaskingSaltUnavailableError,
    require_salts,
)
from pilos.collection.logging_setup import setup_logging
from pilos.storage import manifest
from pilos.storage.comment_db import (
    CommentDBUnavailableError,
    require_connection,
)
from pilos.jobs.preprocess_comments import preprocess_one_source_file
from pilos.storage.preprocess_db import select_source_file_by_name
from pilos.storage.json_io import get_comment_file, to_data_relative

logger = logging.getLogger(__name__)

# ==========================================================================
# 설정 (여기 값만 바꿔서 실행)
# ==========================================================================
# 백필 하한 날짜 "YYYY-MM-DD". 이 날짜 00:00(KST) 이전 댓글을 만나면 종료한다.
# 명령행 --until-date 미지정 시 기본값으로 쓰인다.
UNTIL_DATE = RESUME_UNTIL_DATE
# 수집한 새 댓글을 전처리해 DB(preprocessed_comment 테이블)에도 적재할지 여부.
# True 면 .env 의 DB_* 설정으로 접속한다. 대상 종목 목록도 DB(select_stock)에서 읽으므로
# DB 접속은 필수다. 접속에 실패하면 이번 실행은 크롤링 시작 전에 명시적 오류로 중단한다
# (require_connection → CommentDBUnavailableError). False 로 두면 종목 조회 자체가 불가능하다.
ENABLE_DB = True
# comments 테이블을 없을 때 자동 생성할지(CREATE TABLE IF NOT EXISTS).
# 운영 DB 등 스키마를 코드가 건드리면 안 되는 환경에선 False 로 끈다(테이블 이미 있다고 가정).
# ==========================================================================


def _valid_date(value: str) -> str:
    """--until-date 값이 YYYY-MM-DD 형식인지 검증한다(아니면 argparse 오류)."""
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError(f"날짜는 YYYY-MM-DD 형식이어야 합니다: {value!r}")
    return value


def _filter_targets(targets, target):
    """target 선택에 따라 종목 목록을 거른다(각 행 [2]=subjectId 기준).

    - 'sk'     : SK하이닉스(SK_HYNIX_ID)만
    - 'others' : SK하이닉스를 제외한 그 외 전체
    - 'all' / None : 전체 10개 종목
    """
    if target == "sk":
        return [s for s in targets if s[2] == SK_HYNIX_ID]
    if target == "others":
        return [s for s in targets if s[2] != SK_HYNIX_ID]
    return list(targets)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m pilos.jobs.backfill_comments",
        description="지정 종목을 최신부터 하한 날짜까지 과거로 수집(백필)한다.",
    )
    parser.add_argument(
        "-u", "--until-date",
        type=_valid_date,
        default=UNTIL_DATE,
        metavar="YYYY-MM-DD",
        help=f"백필 하한 날짜. 이 날짜 00:00(KST) 이전 댓글에서 종료한다. (기본값: {UNTIL_DATE})",
    )
    parser.add_argument(
        "-t", "--target",
        choices=["sk", "others", "all"],
        default="all",
        help="수집 대상 종목: 'sk'=SK하이닉스, 'others'=그 외 전체, 'all'=전체(기본값).",
    )
    parser.add_argument(
        "-r", "--reset-cursor",
        action="store_true",
        default=False,
        help="직전 백필 커서를 무시하고 최신(현재 시점)부터 하한 날짜까지 전수 재수집한다.",
    )
    return parser.parse_args(argv)


def _make_stop_when(until_date):
    """until_date 00:00(KST) 이전 댓글에서 종료하는 stop_when 을 만든다."""
    floor = datetime.strptime(until_date, "%Y-%m-%d").replace(tzinfo=KST)

    def stop_when(comment):
        """createdAt 이 하한 이전이면 True(크롤러가 None 은 걸러줌)."""
        return datetime.fromisoformat(comment["createdAt"]) < floor

    return stop_when


def main(until_date: str = UNTIL_DATE, target: str | None = None, reset_cursor: bool = False):
    """지정 종목을 until_date 하한까지 백필한다(종목별 오류는 격리).

    until_date: 하한 날짜 "YYYY-MM-DD"(기본 UNTIL_DATE).
    target: 'sk'=SK하이닉스, 'others'=그 외 전체, None=전체(프로그램 호출).
    reset_cursor: True 면 직전 커서를 무시하고 최신부터 전수 재수집(소급 캐치업).
    성공(done)이 아닌 종목이 하나라도 있으면 종료코드 1을 반환한다(스케줄 실패 감지용).
    """
    setup_logging()
    stop_when = _make_stop_when(until_date)
    target_date = until_date.replace("-", "")        # "2026-06-01" → "20260601"
    # 비식별화 솔트가 없으면 댓글 루프 중간에 TypeError 로 죽으므로, 크롤링 시작 전에
    # 종료코드 1 로 명확히 중단한다(3.4). DB 필수 검증과 같은 시작 단계 fail-fast 계약이다.
    try:
        require_salts()
    except MaskingSaltUnavailableError as e:
        logger.error(f"[백필 종료] 비식별화 솔트 미설정으로 수집을 시작하지 못함: {e}")
        return 1
    # DB 적재기를 반드시 확보한다(종목 목록을 DB 에서 읽으므로 DB 필수). 확보 실패면 조용한
    # None → AttributeError 로 죽지 않고, 크롤링 시작 전에 종료코드 1 로 명확히 중단한다.
    try:
        db_connecter = require_connection(ENABLE_DB)
    except CommentDBUnavailableError:
        logger.error("[백필 종료] DB 접속 실패로 수집을 시작하지 못함(DB 필수)")
        return 1

    TARGETS = _filter_targets(db_connecter.select_stock(), target)
    logger.info(f"[백필 시작] 대상 {len(TARGETS)}종목, 하한 {until_date}, target={target or '전체'}, reset_cursor={reset_cursor}")
    failures = []
    for stock in TARGETS:
        stock_id = stock[0]
        stock_name = stock[1]
        stock_subject_id = stock[2]
        out_file = get_comment_file(stock_name, target_date)
        logger.info(f"===== {stock_name}({stock_subject_id}) 백필 =====")
        failed = False                             # 이 종목이 이미 실패로 집계됐는지(중복 집계 방지)
        try:
            stock_info = {"stock_subject_id": stock_subject_id, "stock_name": stock_name}
            # out_file 은 넘긴 대상 파일과 동일한 Path(수집분을 append 한 파일).
            result, out_file = crawl_until_date(stock_info, out_file, stop_when, reset_cursor=reset_cursor)
            m = manifest.record_run(stock_name, stock_subject_id, result)  # 상태/커버리지 기록
            gaps = manifest.find_coverage_gaps(m)              # 날짜 공백 점검(Q3)
            if gaps:
                logger.warning(f"[{stock_name}] 커버리지 날짜 공백 {len(gaps)}일(예: {gaps[:5]}) "
                               f"- 수집 누락 가능성 점검 필요")
            if result.status != "done":
                failures.append(f"{stock_name}={result.stop_reason}")
                failed = True
        except Exception:
            # 한 종목이 실패해도 나머지 종목은 계속 진행한다.
            logger.exception(f"{stock_name}({stock_subject_id}) 백필 중 오류 - 다음 종목으로 진행")
            failures.append(f"{stock_name}=exception")
            failed = True

        # DB 적재: 원본 파일 메타데이터를 source_comment_file 에 등록(종목별 오류 격리).
        # insert_source 는 실패 시 예외를 던지므로(반환값 아님) 성공 여부는 예외로 판단한다.
        try:
            file_str = str(out_file.name)
            file_path = to_data_relative(out_file.parent)   # 절대경로 대신 "raw" 같은 상대경로
            file_name = file_str.split(".")[0]
            file_ext = file_str.split(".")[1] if "." in file_str else ""
            file_source = {
                "stock_id" : stock_id,
                "file_path" : file_path,
                "file_name" : file_name,
                "file_ext" : file_ext,
                "platform" : "TOSS"
            }
            db_connecter.insert_source(file_source)
            logger.info(f"[DB 적재] 성공 / 종목명 : {stock_name}")

            # 백필 직후 preprocessed_comment 테이블에 즉시 전처리 적재
            try:
                source_rec = select_source_file_by_name(file_name)
                if source_rec:
                    inserted = preprocess_one_source_file(source_rec)
                    logger.info(f"[전처리 적재] 성공 / 종목명 : {stock_name}, 신규 적재 건수: {inserted}")
            except Exception:
                logger.exception(f"[전처리 적재] 실패 / 종목명 : {stock_name}")
        except Exception:
            logger.exception(f"[DB 적재] 실패 / 종목명 : {stock_name}")
            if not failed:                         # 크롤링 단계에서 이미 집계됐으면 중복 집계 안 함
                failures.append(f"{stock_name}=db_insert")
    ok = len(TARGETS) - len(failures)
    if failures:
        logger.error(f"[백필 종료] 성공 {ok}/{len(TARGETS)} · 실패/중단 {len(failures)}: {failures}")
        return 1
    logger.info(f"[백필 종료] 성공 {ok}/{len(TARGETS)}")
    return 0


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(main(until_date=args.until_date, target=args.target, reset_cursor=args.reset_cursor))
