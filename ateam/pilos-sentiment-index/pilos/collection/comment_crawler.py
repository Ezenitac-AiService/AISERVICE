import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

from pilos.collection.constants import (
    BASE_TIME,
    BASE_URL,
    MAX_RETRY,
    REQUEST_TIMEOUT,
    USER_AGENT,
)
from pilos.collection.data_masking import anonymize_nickname, anonymize_user_profile_id
from pilos.storage import comment_store, manifest

# 로깅 핸들러 설정은 실행기(jobs/*.main)에서 setup_logging 으로 한 번만 한다(P3-5).
logger = logging.getLogger(__name__)


#=============================================================================
# 종료 사유 / 실행 결과
#=============================================================================
STOP_EMPTY = "empty"                   # 더 이상 댓글이 없어 자연 종료
STOP_CURSOR_STUCK = "cursor_stuck"     # 커서가 진행되지 않아 종료
STOP_REACHED_DATE = "reached_date"     # 백필: 목표 날짜 도달
STOP_REACHED_RECENT = "reached_recent" # 증분: 직전 실행 최신 지점 도달
STOP_FETCH_FAILED = "fetch_failed"     # 재시도 후에도 요청 실패


@dataclass
class CrawlResult:
    stock: str
    mode: str            # "backfill" | "incremental"
    pages: int
    collected: int       # 실제로 새로 기록한 건수
    stop_reason: str
    status: str          # "done" | "interrupted" (P1-1)
    final_cursor: object
    elapsed_sec: float
    daily_counts: dict = field(default_factory=dict)   # 작성일(YYYYMMDD)별 기록 건수


# 목표 하한 도달·이력 소진은 완료, 실패·커서정지는 중단으로 본다 (P1-1).
_DONE_REASONS = (STOP_REACHED_DATE, STOP_REACHED_RECENT, STOP_EMPTY)


def _status_for(stop_reason):
    """종료 사유를 done/interrupted 상태로 매핑한다(P1-1)."""
    return "done" if stop_reason in _DONE_REASONS else "interrupted"


def _build_url(subject_id):
    """subjectId 로 최신순 댓글 요청 URL 을 만든다."""
    return f"{BASE_URL}?subjectType=STOCK&subjectId={subject_id}&commentSortType=RECENT"


def _fetch_comments(target_url, headers):
    """요청을 보내 댓글 리스트를 반환한다(일시 오류는 MAX_RETRY 재시도, 실패 시 None; 429는 Retry-After 존중, P1-2)."""
    for attempt in range(1, MAX_RETRY + 1):
        try:
            response = requests.get(target_url, headers=headers, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            logger.warning(f"요청 실패({attempt}/{MAX_RETRY}): {e}")
            time.sleep(attempt * 2)
            continue

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            wait = int(retry_after) if retry_after and retry_after.isdigit() else attempt * 3
            logger.warning(f"레이트리밋(429) - {wait}초 대기 후 재시도({attempt}/{MAX_RETRY})")
            time.sleep(wait)
            continue
        if response.status_code != 200:
            logger.warning(f"접속 실패(status={response.status_code})({attempt}/{MAX_RETRY})")
            time.sleep(attempt * 2)
            continue

        try:
            return response.json()['result']['results']
        except (ValueError, KeyError) as e:
            logger.warning(f"응답 파싱 실패({attempt}/{MAX_RETRY}): {e}")
            time.sleep(attempt * 2)
            continue

    return None


def _sanitize_and_mask_comment(comment: dict) -> None:
    """댓글의 작성자 필드가 비어있어도 안전하게 fallback 처리하고 비식별화한다."""
    author = comment.get('author')
    if not isinstance(author, dict):
        author = {}
        comment['author'] = author

    profile_id = author.get('userProfileId') or comment.get('authorUserProfileId')
    nickname = author.get('nickname')

    masked_profile_id = anonymize_user_profile_id(profile_id)
    masked_nickname = anonymize_nickname(nickname)

    comment['author']['userProfileId'] = masked_profile_id
    comment['author']['nickname'] = masked_nickname
    comment['authorUserProfileId'] = masked_profile_id


def _select_page(comments, seen_ids, should_stop):
    """한 페이지에서 저장할 새 댓글(대댓글 포함)을 고른다 → (last_cursor, stopped, new_comments) (파일 I/O 없음)."""
    last_cursor = None
    new_comments = []

    for comment in comments:
        cid = comment.get('commentId')
        if cid is None:
            continue

        # 최상위 댓글 id로 페이지네이션 커서를 갱신한다.
        last_cursor = cid

        # 대댓글(답글) 목록 추출
        raw_replies = comment.get('replies') or comment.get('subComments') or comment.get('nestedComments') or []

        # 최상위 댓글 비식별화 및 처리
        _sanitize_and_mask_comment(comment)

        try:
            if should_stop(comment):
                return last_cursor, True, new_comments
        except Exception:
            logger.exception(f"댓글(id={cid}) 정지 조건 검사 실패 - 건너뜀")
            continue

        if comment.get('createdAt') is not None and cid not in seen_ids:
            seen_ids.add(cid)
            new_comments.append(comment)

        # 대댓글 평탄화 (각 대댓글도 독립 댓글 레코드로 수집)
        if isinstance(raw_replies, list):
            for reply in raw_replies:
                if not isinstance(reply, dict):
                    continue
                r_cid = reply.get('commentId')
                if r_cid is None:
                    continue

                _sanitize_and_mask_comment(reply)

                try:
                    if should_stop(reply):
                        return last_cursor, True, new_comments
                except Exception:
                    continue

                if reply.get('createdAt') is not None and r_cid not in seen_ids:
                    seen_ids.add(r_cid)
                    new_comments.append(reply)

    return last_cursor, False, new_comments


def crawl_until_date(stock:dict, out_file, stop_when, base_time=BASE_TIME, reset_cursor: bool = False):
    """최신순으로 과거로 페이지네이션하며 stop_when 지점까지 수집한다(백필, 재개 지점 저장).

    외부 API 요청과 원본 JSONL append 까지만 담당한다(collection 책임). 전처리·DB 적재는
    수행하지 않으며, 수집 결과의 DB 등록은 호출한 jobs 실행기가 조합한다.

    반환 : (CrawlResult, out_file). out_file 은 수집분을 append 한 대상 파일 Path.
    """
    stock_subject_id = stock["stock_subject_id"]
    stock_name = stock["stock_name"]
    start = time.monotonic()

    comment_store.seal_trailing_newline(out_file)          # P1-3: 잘린 줄 격리
    seen_ids = comment_store.load_seen_comment_ids(out_file)  # P2-1: 꼬리 dedup
    cursor = None if reset_cursor else manifest.load_backfill_cursor(stock_name)
    if not reset_cursor and manifest.load_backfill_status(stock_name) == "done":
        logger.info(f"[{stock_name}] 직전 백필이 완료(done) 상태 - 목표 하한을 확장했다면 이어서 진행")

    url = _build_url(stock_subject_id)
    headers = {"user-agent": USER_AGENT}
    if cursor is not None:
        logger.info(f"[{stock_name}] 이어서 재개 last_comment_id={cursor}")

    # createdAt 이 없으면 stop 판정을 건너뛰도록 감싼다(원본 순서/의미 보존).
    def _stop(comment):
        if comment.get('createdAt') is None:
            return False
        return stop_when(comment)

    pages = 0
    collected = 0
    daily_counts = {}        # 작성일(YYYYMMDD)별 기록 건수
    prev_cursor = None
    stop_reason = STOP_EMPTY
    while True:
        pages += 1
        logger.debug(f"[{stock_name}] {pages}페이지 수집 중")

        target_url = url if cursor is None else f"{url}&lastCommentId={cursor}"
        comments = _fetch_comments(target_url, headers)
        if comments is None:
            logger.error(f"[{stock_name}] 재시도 후에도 실패하여 종료")
            manifest.save_backfill_cursor(stock_name, cursor)   # 재개 지점 저장
            stop_reason = STOP_FETCH_FAILED
            break
        if not comments:
            stop_reason = STOP_EMPTY
            break

        last_cursor, stopped, new_comments = _select_page(comments, seen_ids, _stop)
        comment_store.append_comments(out_file, new_comments)   # 원본 우선 저장

        collected += len(new_comments)
        for c in new_comments:                             # 작성일별 카운트 누적
            key = comment_store.created_date_key(c)
            daily_counts[key] = daily_counts.get(key, 0) + 1
        if last_cursor is not None:
            cursor = last_cursor
        manifest.save_backfill_cursor(stock_name, cursor)  # 진행/정지 지점 저장

        if stopped:
            stop_reason = STOP_REACHED_DATE
            break
        # 커서가 직전과 같으면(=페이지가 더 안 넘어감) 무한루프 방지로 종료한다.
        if cursor == prev_cursor:
            stop_reason = STOP_CURSOR_STUCK
            break
        prev_cursor = cursor

        time.sleep(base_time + random.uniform(-0.2, 0.5))

    status = _status_for(stop_reason)
    manifest.save_backfill_status(stock_name, status)       # P1-1: 완료/중단 상태 저장
    result = CrawlResult(stock_name, "backfill", pages, collected, stop_reason, status, cursor,
                         time.monotonic() - start, daily_counts)
    logger.info(f"[{stock_name}] 완료 | mode=backfill 상태={status} 수집={collected} 페이지={pages} "
                f"사유={stop_reason} 소요={result.elapsed_sec:.1f}s 커서={cursor}")
    return result, out_file


def crawl_from_now(stock:dict, out_file_for, base_time=BASE_TIME) -> tuple[CrawlResult, list[Path]]:
    """최신순으로 직전 실행 최신 지점까지 새 댓글만 수집한다(증분).

    out_file_for : callable(date_key 'YYYYMMDD') -> Path. 댓글 createdAt 날짜로 저장 파일을
                   고른다(작성일별 분리 저장). 최신 지점은 정상 종료 시에만 확정(P0-1).

    외부 API 요청과 원본 JSONL append 까지만 담당한다(collection 책임). 전처리·DB 적재는
    수행하지 않으며, 수집 결과의 DB 등록은 호출한 jobs 실행기가 조합한다.

    반환 : (CrawlResult, out_files). out_files 는 이번 실행에서 실제로 기록한 작성일별
           파일들의 Path 리스트(작성일 오름차순, 기록이 없으면 빈 리스트).
    """
    stock_subject_id = stock["stock_subject_id"]
    stock_name = stock["stock_name"]
    start = time.monotonic()

    connecter = comment_store.DatePartitionedAppender(out_file_for, stock_name)  # createdAt 날짜별 파일 라우팅
    end_before_id = manifest.load_recent_id(stock_name)

    url = _build_url(stock_subject_id)
    headers = {"user-agent": USER_AGENT}

    # 직전 실행에서 이미 수집한 최신 지점에 도달하면 종료한다(id 임계값, createdAt 무관).
    # commentId 는 단조 증가 정수라 '<=' 로 비교한다. '==' 로는 경계 댓글이 삭제·필터되면
    # 매칭을 놓쳐 과거 전체를 재크롤하지만, '<=' 는 그보다 오래된 첫 댓글에서 안전히 멈춘다.
    def _stop(comment):
        cid = comment.get('commentId')
        return end_before_id is not None and cid is not None and cid <= end_before_id

    pages = 0
    collected = 0
    cursor = None            # 페이지네이션 커서(None이면 최신부터)
    prev_cursor = None
    pending_recent = None    # 이번 실행 최신 id. 정상 종료 시에만 확정 저장(P0-1)
    seen_ids = set()         # 실행 내 중복 방지(파일 간 dedup 은 connecter 가 담당)
    stop_reason = STOP_EMPTY
    while True:
        pages += 1
        logger.debug(f"[{stock_name}] {pages}페이지 수집 중")

        target_url = url if cursor is None else f"{url}&lastCommentId={cursor}"
        comments = _fetch_comments(target_url, headers)
        if comments is None:
            logger.error(f"[{stock_name}] 재시도 후에도 실패하여 종료")
            stop_reason = STOP_FETCH_FAILED
            break                                          # recent 확정하지 않음(P0-1)
        if not comments:
            stop_reason = STOP_EMPTY
            break

        # 첫 페이지의 최신 id를 '기억'만 한다(아직 저장하지 않음).
        if pending_recent is None:
            pending_recent = comments[0].get('commentId')

        last_cursor, stopped, new_comments = _select_page(comments, seen_ids, _stop)
        collected += connecter.append(new_comments)           # createdAt 날짜별 저장 + 기록 건수(원본 우선)

        if last_cursor is not None:
            cursor = last_cursor

        if stopped:
            stop_reason = STOP_REACHED_RECENT
            break
        # 커서가 직전과 같으면(=페이지가 더 안 넘어감) 무한루프 방지로 종료한다.
        if cursor == prev_cursor:
            stop_reason = STOP_CURSOR_STUCK
            break
        prev_cursor = cursor

        time.sleep(base_time + random.uniform(-0.2, 0.5))

    # done 종료(최신 도달 / 이력 소진)에서만 최신 지점을 확정한다(P0-1).
    # 커서 정지(interrupted)는 경계 미도달일 수 있어 확정하지 않는다(gap 방지).
    if stop_reason in _DONE_REASONS and pending_recent is not None:
        manifest.save_recent_id(stock_name, pending_recent)

    status = _status_for(stop_reason)
    result = CrawlResult(stock_name, "incremental", pages, collected, stop_reason, status, cursor,
                         time.monotonic() - start, dict(connecter.written))
    out_files = connecter.written_paths()   # 이번 실행에서 실제로 기록한 작성일별 파일 Path 목록
    logger.info(f"[{stock_name}] 완료 | mode=incremental 상태={status} 수집={collected} 페이지={pages} "
                f"사유={stop_reason} 소요={result.elapsed_sec:.1f}s 커서={cursor}")
    return result, out_files
