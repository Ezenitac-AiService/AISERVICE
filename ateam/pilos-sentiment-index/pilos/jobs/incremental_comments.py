"""증분 실행기: 지정 종목의 직전 수집 이후 새 댓글만 수집한다.

명령행 인자로 대상 종목을 지정한다.
실행 예:
  uv run python -m pilos.jobs.incremental_comments --target sk
  uv run python -m pilos.jobs.incremental_comments --target others
"""
import argparse
import logging
import sys
import time
from dataclasses import dataclass, field

from pilos.collection.comment_crawler import crawl_from_now
from pilos.collection.constants import SK_HYNIX_ID
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
from pilos.storage.json_io import (
    get_incremental_comment_file,
    to_data_relative,
)

logger = logging.getLogger(__name__)


def _filter_targets(targets, target):
    """target 선택에 따라 종목 목록을 거른다(각 행 [2]=subjectId 기준).

    - 'sk'     : SK하이닉스(SK_HYNIX_ID)만
    - 'others' : SK하이닉스를 제외한 그 외 전체
    - None     : 전체(최상위 실행기 등 프로그램 호출용 기본값)
    """
    if target == "sk":
        return [s for s in targets if s[2] == SK_HYNIX_ID]
    if target == "others":
        return [s for s in targets if s[2] != SK_HYNIX_ID]
    return list(targets)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m pilos.jobs.incremental_comments",
        description="지정 종목의 직전 수집 이후 새 댓글만 수집(증분)한다.",
    )
    parser.add_argument(
        "-t", "--target",
        choices=["sk", "others"],
        required=True,
        help="수집 대상 종목: 'sk'=SK하이닉스, 'others'=그 외 전체.",
    )
    return parser.parse_args(argv)


def _seed_recent_boundary(name):
    """recent_comment_id 가 없으면 증분 경계를 세운다(이미 있으면 no-op).

    경계값은 init_manifest 와 동일한 규칙(manifest.recent_id_from_files)으로 구한다:
    from_ 파일에 유효 댓글이 있으면 from_ 파일 전체의 최댓값 commentId, 없으면
    until_(백필) 파일 전체의 최댓값. 첫 증분이 이미 모은 최신 지점까지만 긁도록
    (전체 이력 재수집 방지) 경계를 세운다.
    """
    if manifest.load_recent_id(name) is not None:
        return

    cid = manifest.recent_id_from_files(name)
    if cid is not None:
        manifest.save_recent_id(name, cid)
        logger.info(f"[{name}] 증분 경계 없음 → 수집 파일 전체 최댓값 {cid} 로 초기화")
    else:
        logger.warning(f"[{name}] from_·백필 파일이 없어 경계를 세우지 못함(전체 이력 대상)")

# ==========================================================================
# 설정 (여기 값만 바꿔서 실행)
# ==========================================================================
# 수집 대상 종목은 아래 상수가 아니라 DB(select_stock)에서 읽어온다(main 참조).

# 수집한 새 댓글을 전처리해 DB(preprocessed_comment 테이블)에도 적재할지 여부.
# True 면 .env 의 DB_* 설정으로 접속한다. 대상 종목 목록도 DB(select_stock)에서 읽으므로
# DB 접속은 필수다. 접속에 실패하면 이번 실행은 크롤링 시작 전에 명시적 오류로 중단한다
# (require_connection → CommentDBUnavailableError). False 로 두면 DB 를 만들지 않아 종목
# 조회 자체가 불가능하므로 실행할 수 없다.
ENABLE_DB = True
# comments 테이블을 없을 때 자동 생성할지(CREATE TABLE IF NOT EXISTS).
# 운영 DB 등 스키마를 코드가 건드리면 안 되는 환경에선 False 로 끈다(테이블 이미 있다고 가정).
# ==========================================================================


@dataclass
class StockIncrementalResult:
    """증분 수집 종목 1건의 관측 결과(최상위 실행기·운영 로그용).

    수집 엔진(CrawlResult)이 이미 만든 종목별 관측값을 실행기 요약까지 끌어올려,
    최상위 실행기가 API 사용량(페이지)·실행시간·종료 사유·증분 재개 상태를 판단하게 한다.
    크롤링이 예외로 끝난 종목은 status='exception' 이고 수치는 0/None 이다.
    """
    stock_name: str
    stock_subject_id: str
    status: str                 # "done" | "interrupted" | "exception"
    collected: int              # 이 종목 신규 기록(원본 append) 건수
    pages: int                  # 요청 페이지 수(API 사용량 추정)
    elapsed_sec: float          # 종목별 수집 소요 시간
    stop_reason: str | None     # 크롤러 종료 사유(예외로 끝나면 None)
    recent_boundary: object     # 실행 후 확정된 증분 경계(recent_comment_id); 미확정이면 None
    out_files: list             # 이번 실행이 기록한 작성일별 파일 Path 목록(전처리 대상)
    db_insert_failed: bool      # source_comment_file 등록 실패 여부
    failure_reason: str | None  # 대표 실패 사유("<stop_reason>"|"exception"|"db_insert"); 성공이면 None


@dataclass
class IncrementalRunSummary:
    """증분 수집 한 회 실행 결과 요약.

    최상위 실행기가 부분 실패를 감지하고 관측 로그를 남길 수 있도록,
    종료코드(0/1) 하나가 아니라 종목 단위 성패와 수집 건수를 함께 담는다.
    종목별 세부 관측(페이지·실행시간·종료 사유·증분 경계)은 stocks 에 담는다.
    반환 자료형은 이 실행기 내부 계약이며 영역 간 공통 DTO가 아니다.
    """
    total: int                                          # 대상 종목 수
    succeeded: int                                      # done 종목 수
    failed: int                                         # 실패·중단 종목 수
    collected: int                                      # 전체 신규 기록(원본 append) 건수
    failures: list[str] = field(default_factory=list)   # "종목명=사유" 목록
    elapsed_sec: float = 0.0                             # 전체 실행시간(10분 주기 가능성 측정)
    stocks: list[StockIncrementalResult] = field(default_factory=list)  # 종목별 관측 결과

    @property
    def exit_code(self) -> int:
        """하나라도 실패·중단이면 1, 전부 성공이면 0(스케줄러 실패 감지용)."""
        return 1 if self.failures else 0

    @property
    def total_pages(self) -> int:
        """전체 종목 요청 페이지 수 합(API 사용량 추정용)."""
        return sum(s.pages for s in self.stocks)

    @property
    def recorded_files(self) -> list:
        """이번 실행에서 실제로 기록한 작성일별 파일 Path 전체(종목·작성일 순).

        최상위 실행기가 '오늘 날짜' 재탐색 대신 이 목록을 전처리에 직접 넘겨,
        과거 작성일 파일에 늦게 append 된 지연 댓글도 누락 없이 전처리한다(3.7).
        """
        return [p for s in self.stocks for p in s.out_files]


def run_incremental(target: str | None = None) -> IncrementalRunSummary:
    """지정 종목의 새 댓글만 증분 수집한다(댓글 작성일별 파일 분리, 종목별 오류는 격리).

    target: 'sk'=SK하이닉스, 'others'=그 외 전체, None=전체(프로그램 호출).
    성공(done)이 아닌 종목이 하나라도 있으면 summary.exit_code 가 1이 된다(스케줄 실패 감지용).
    """
    # 비식별화 솔트가 없으면 댓글 루프 중간에 TypeError 로 죽으므로, 크롤링 시작 전에
    # 명시 중단한다(3.4). require_connection 과 같은 시작 단계 fail-fast 계약이다.
    require_salts()
    # DB 적재기를 반드시 확보한다. 확보 실패면 여기서 CommentDBUnavailableError 로 중단하고
    # (종목 목록을 DB 에서 읽으므로 DB 필수), 조용한 None → AttributeError 로 죽지 않는다.
    db_connecter = require_connection(ENABLE_DB)
    # 대상 종목 목록을 DB 에서 읽는다: (stock_id, 종목명, subjectId) 튜플의 시퀀스.
    TARGETS = _filter_targets(db_connecter.select_stock(), target)
    logger.info(f"[증분 시작] 대상 {len(TARGETS)}종목, target={target or '전체'}")
    run_start = time.monotonic()           # 전체 실행시간 측정 시작(10분 주기 가능성 판단용)
    failures = []                          # 실패/중단한 종목 사유 모음(종료코드 판정용)
    collected_total = 0                    # 전체 종목 신규 기록 건수 합(관측·부분실패 판단용)
    stock_results = []                     # 종목별 관측 결과(페이지·소요·사유·경계)

    for stock in TARGETS:
        stock_id = stock[0]
        stock_name = stock[1]
        stock_subject_id = stock[2]
        _seed_recent_boundary(stock_name)   # 첫 실행이면 from_ 최신(없으면 백필) 지점을 경계로 설정
        # 댓글 createdAt 날짜(YYYYMMDD)로 저장 파일을 고른다.
        # _name 을 기본인자로 바인딩해 현재 종목명을 캡처한다(루프 클로저 late-binding 방지).
        # 크롤러의 날짜별 적재기(DatePartitionedAppender)가 out_file_for(key, _name=...) 로 호출한다.
        def out_file_for(date_key, _name=stock_name):
            return get_incremental_comment_file(_name, date_key)
        logger.info(f"===== {stock_name}({stock_subject_id}) 증분 =====")
        failed = False                 # 이 종목이 이미 실패로 집계됐는지(중복 집계 방지)
        failure_reason = None          # 이 종목의 대표 실패 사유(성공이면 None)
        out_files = []                 # 크롤링이 예외로 끝나면 기록 파일 없음(빈 목록)
        # 크롤링이 예외로 끝나도 관측 레코드를 남기도록 기본값을 둔다(status='exception').
        stock_status = "exception"
        pages = 0
        collected = 0
        elapsed_sec = 0.0
        stop_reason = None
        db_insert_failed = False
        try:
            # 크롤러는 종목명+subjectId 를 dict 로 받는다(파일 라우팅에 종목명이 필요).
            stock_info = {"stock_subject_id": stock_subject_id, "stock_name": stock_name}
            # out_files: 이번 실행에서 실제로 기록한 작성일별 파일 Path 목록
            result, out_files = crawl_from_now(stock_info, out_file_for)
            collected_total += result.collected            # 신규 기록 건수 누적(관측·부분실패 판단용)
            # 크롤러가 이미 만든 종목별 관측값을 실행기 요약으로 끌어올린다.
            stock_status = result.status
            pages = result.pages
            collected = result.collected
            elapsed_sec = result.elapsed_sec
            stop_reason = result.stop_reason
            logger.debug(f"[{stock_name}] 기록 파일 {len(out_files)}개: {[p.name for p in out_files]}")
            # [변경 2026-08-03] record_run(델타 누적) → update_from_files(파일 스캔, self-heal).
            #   이번 실행이 쓴 out_files 만 스캔해 일별 카운트를 절대값으로 갱신하고,
            #   recent_id 는 done 일 때만 from_ 파일 기준으로 갱신한다(P0-1).
            m = manifest.update_from_files(stock_name, stock_subject_id, result, out_files)
            gaps = manifest.find_coverage_gaps(m)              # 날짜 공백 점검(Q3)
            if gaps:
                logger.warning(f"[{stock_name}] 커버리지 날짜 공백 {len(gaps)}일(예: {gaps[:5]}) "
                               f"- 수집 누락 가능성 점검 필요")
            # done 이 아니면(중단·실패) 실패 목록에 사유와 함께 기록한다.
            if result.status != "done":
                failures.append(f"{stock_name}={result.stop_reason}")
                failed = True
                failure_reason = result.stop_reason
        except Exception:
            # 한 종목이 실패해도 나머지 종목은 계속 진행한다(종목별 오류 격리).
            logger.exception(f"{stock_name}({stock_subject_id}) 증분 중 오류 - 다음 종목으로 진행")
            failures.append(f"{stock_name}=exception")
            failed = True
            failure_reason = "exception"

        # DB 적재: 작성일별로 기록된 각 파일의 메타데이터를 source_comment_file 에 등록(파일별 오류 격리).
        # insert_source 는 실패 시 예외를 던지므로(반환값 아님) 성공 여부는 예외로 판단한다.
        for out_file in out_files:
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
                logger.info(f"[DB 적재] 성공 / 종목명 : {stock_name} ({file_name})")
            except Exception:
                logger.exception(f"[DB 적재] 실패 / 종목명 : {stock_name} ({out_file.name})")
                db_insert_failed = True
                if not failed:                         # 크롤링/앞선 파일에서 이미 집계됐으면 중복 집계 안 함
                    failures.append(f"{stock_name}=db_insert")
                    failed = True
                    failure_reason = "db_insert"

        # 실행 후 확정된 증분 경계(recent_comment_id). done 종료에서만 앞당겨진다(P0-1) →
        # 최상위 실행기가 증분 재개 상태(중단 종목은 다음 실행이 어디부터 다시 긁는지)를 관측.
        recent_boundary = manifest.load_recent_id(stock_name)
        stock_results.append(StockIncrementalResult(
            stock_name=stock_name,
            stock_subject_id=stock_subject_id,
            status=stock_status,
            collected=collected,
            pages=pages,
            elapsed_sec=elapsed_sec,
            stop_reason=stop_reason,
            recent_boundary=recent_boundary,
            out_files=list(out_files),
            db_insert_failed=db_insert_failed,
            failure_reason=failure_reason,
        ))
        logger.info(f"[관측] {stock_name} 상태={stock_status} 수집={collected} 페이지={pages} "
                    f"소요={elapsed_sec:.1f}s 사유={stop_reason} 파일={len(out_files)} "
                    f"경계={recent_boundary}"
                    + (" · DB적재실패" if db_insert_failed else ""))

    ok = len(TARGETS) - len(failures)          # 성공 종목 수
    total_elapsed = time.monotonic() - run_start
    summary = IncrementalRunSummary(
        total=len(TARGETS),
        succeeded=ok,
        failed=len(failures),
        collected=collected_total,
        failures=failures,
        elapsed_sec=total_elapsed,
        stocks=stock_results,
    )
    # 하나라도 실패/중단이면 exit_code 1(스케줄러가 실패로 감지하도록).
    if failures:
        logger.error(f"[증분 종료] 성공 {ok}/{len(TARGETS)} · 실패/중단 {len(failures)} "
                     f"· 수집 {collected_total}건 · 페이지 {summary.total_pages} "
                     f"· 소요 {total_elapsed:.1f}s: {failures}")
    else:
        logger.info(f"[증분 종료] 성공 {ok}/{len(TARGETS)} · 수집 {collected_total}건 "
                    f"· 페이지 {summary.total_pages} · 소요 {total_elapsed:.1f}s")
    return summary


def main(target: str | None = None) -> int:
    """CLI·스케줄러용 얇은 래퍼. 종료코드(0/1)만 반환해 기존 호출부와 호환된다.

    성공·실패 종목 수와 수집 건수 등 풍부한 결과가 필요한 최상위 실행기는
    run_incremental()을 직접 호출한다(그쪽은 DB 필수 위반을 예외로 전달한다).
    여기서는 DB 초기화 실패를 종료코드 1 로 변환해 int 계약을 유지한다.
    """
    setup_logging()
    try:
        return run_incremental(target).exit_code
    except MaskingSaltUnavailableError as e:
        logger.error(f"[증분 종료] 비식별화 솔트 미설정으로 수집을 시작하지 못함: {e}")
        return 1
    except CommentDBUnavailableError:
        logger.error("[증분 종료] DB 접속 실패로 수집을 시작하지 못함(DB 필수)")
        return 1


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(main(target=args.target))
