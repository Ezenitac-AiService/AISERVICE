"""종목별 수집 상태 매니페스트(JSON)의 갱신·조회 (storage 계층).

한 종목의 수집이 여러 파일(until_*, from_*)로 흩어지므로, "어디까지·언제·얼마나"
모았는지를 한곳에 요약해 둔다. 운영(마지막 성공 시각·중단 여부)과 분석(커버리지
하한·일별 건수)의 공통 진입점이다. CrawlResult 를 병합해 누적한다.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pilos.storage import comment_store
from pilos.storage.json_io import (
    _load_json,
    atomic_write_json,
    get_data_dir,
    get_data_file,
)

KST = ZoneInfo("Asia/Seoul")


def _path(stock_name):
    return get_data_file(f"{stock_name}_manifest.json")


def load(stock_name, default=None):
    """저장된 매니페스트를 읽어 반환한다(없거나 손상 시 default)."""
    return _load_json(_path(stock_name), default)


# --- 체크포인트 접근자 (종목별 상태를 매니페스트 단일 파일로 통합) ----------------
# last_comment_id / recent_comment_id / backfill_status 를 별도 파일 대신 modes 아래에 둔다.
# 크롤러가 실행 중(백필은 매 페이지) 이 값을 갱신하고, 조회는 아래 load_* 로 한다.

def _set_mode_field(stock_name, mode, key, value):
    """modes[mode][key] 만 갱신해 매니페스트를 원자적으로 다시 쓴다(load→수정→write)."""
    m = load(stock_name) or {"stock": stock_name, "modes": {}, "daily_counts": {}}
    m.setdefault("modes", {}).setdefault(mode, {})[key] = value
    m["updated_at"] = datetime.now(KST).isoformat(timespec="seconds")
    atomic_write_json(_path(stock_name), m)
    return m


def _get_mode_field(stock_name, mode, key, default=None):
    """modes[mode][key] 를 읽어 반환한다(없으면 default)."""
    m = load(stock_name) or {}
    return (m.get("modes", {}).get(mode) or {}).get(key, default)


def save_backfill_cursor(stock_name, cursor):
    """백필 재개 지점(마지막 처리 commentId)을 저장한다(옛 last_comment_id 대체)."""
    _set_mode_field(stock_name, "backfill", "cursor", cursor)


def load_backfill_cursor(stock_name, default=None):
    """백필 재개 지점을 읽어 반환한다."""
    return _get_mode_field(stock_name, "backfill", "cursor", default)


def save_backfill_status(stock_name, status):
    """백필 종료 상태("done" | "interrupted")를 저장한다(옛 backfill_status 대체, P1-1)."""
    _set_mode_field(stock_name, "backfill", "status", status)


def load_backfill_status(stock_name, default=None):
    """백필 종료 상태를 읽어 반환한다."""
    return _get_mode_field(stock_name, "backfill", "status", default)


def save_recent_id(stock_name, comment_id):
    """증분 종료 경계(직전 실행 최신 commentId)를 저장한다(옛 recent_comment_id 대체, P0-1)."""
    _set_mode_field(stock_name, "incremental", "recent_id", comment_id)


def load_recent_id(stock_name, default=None):
    """증분 종료 경계를 읽어 반환한다."""
    return _get_mode_field(stock_name, "incremental", "recent_id", default)


#=================================================================================
# 데이터에 대한 데이터를 모아놓기
#=================================================================================
def record_run(stock_name, subject_id, result):
    """CrawlResult 를 매니페스트에 병합 저장한다.

    - daily_counts: 작성일별 건수를 '누적'(재실행 시 새로 기록한 만큼만 더해짐)
    - coverage: 누적 일별 카운트의 최소/최대 날짜(수집 하한/최신)
    - modes[mode]: 해당 모드의 마지막 실행 요약
    - last_success_at: status=="done" 인 실행의 시각
    """
    m = load(stock_name) or {"stock": stock_name, "subject_id": subject_id,
                             "modes": {}, "daily_counts": {}}
    now = datetime.now(KST).isoformat(timespec="seconds")
    m["subject_id"] = subject_id
    m["updated_at"] = now

    daily = m.setdefault("daily_counts", {})
    for date_key, n in (result.daily_counts or {}).items():
        daily[date_key] = daily.get(date_key, 0) + n

    # 크롤러가 실행 중 써 둔 cursor/recent_id 를 덮어쓰지 않도록 통째 교체가 아니라 병합한다.
    mode_entry = m.setdefault("modes", {}).setdefault(result.mode, {})
    mode_entry.update({
        "last_run_at": now,
        "status": result.status,
        "stop_reason": result.stop_reason,
        "collected": result.collected,
        "pages": result.pages,
        "final_cursor": result.final_cursor,
    })
    if result.status == "done":
        m["last_success_at"] = now

    if daily:
        keys = sorted(daily)
        m["coverage"] = {"floor_date": keys[0], "latest_date": keys[-1]}

    atomic_write_json(_path(stock_name), m)
    return m


#=================================================================================
# 솔직히 필요한지 모르겠음..
# 클로드가 있어야한다고 해서 만들게 하긴 했는데 굳이 없어도 될 것 같은 함수
#=================================================================================
def find_coverage_gaps(m):
    """coverage floor~latest 사이에서 daily_counts 에 한 건도 없는 날짜(YYYYMMDD)를 반환한다.

    커서 페이지네이션이 한 구간을 통째로 건너뛰면 특정 날짜가 비어 gap 으로 남는다(Q3).
    다만 실제로 댓글이 없던 날도 포함될 수 있는 '휴리스틱 경고'이며, 자동 판정이 아니라
    사람이 수집 누락을 점검하도록 알리는 용도다.
    """
    if not m:
        return []
    daily = m.get("daily_counts") or {}
    coverage = m.get("coverage") or {}
    floor = coverage.get("floor_date")
    latest = coverage.get("latest_date")
    if not floor or not latest:
        return []
    day = datetime.strptime(floor, "%Y%m%d").date()
    end = datetime.strptime(latest, "%Y%m%d").date()
    gaps = []
    while day <= end:
        key = day.strftime("%Y%m%d")
        if key not in daily:
            gaps.append(key)
        day += timedelta(days=1)
    return gaps

#=================================================================================
# 위 함수를 만들기 이전 데이터를 처리하기 위해 만들어진 함수
# 즉 이것도 없어도 될 것 같다
#=================================================================================
def rebuild(stock_name, subject_id, daily_counts, mode_summaries=None):
    """파일 스캔으로 얻은 '절대' 일별 카운트로 매니페스트를 재작성한다(멱등).

    record_run 이 델타를 누적하는 것과 달리, 이 함수는 daily_counts 를 통째로
    덮어써 파일 상태를 진실원본으로 삼는다(manifest 도입 이전 자료 초기화용).
    """
    m = load(stock_name) or {}
    m["stock"] = stock_name
    m["subject_id"] = subject_id
    m["updated_at"] = datetime.now(KST).isoformat(timespec="seconds")
    m["daily_counts"] = dict(daily_counts)
    if mode_summaries:
        m.setdefault("modes", {}).update(mode_summaries)
    if daily_counts:
        keys = sorted(daily_counts)
        m["coverage"] = {"floor_date": keys[0], "latest_date": keys[-1]}
    atomic_write_json(_path(stock_name), m)
    return m


#=================================================================================
# 파일 스캔 기반 갱신 (① 일별 총 댓글 수 ② from_ 기준 recent_id)
#   - rebuild_from_files : 전 파일 통합(초기화/재작성). init_manifest 용.
#   - update_from_files  : 이번 실행이 쓴 파일만(가벼움). incremental 용.
#=================================================================================
def _stock_files(stock_name):
    """종목의 원본 파일을 (until_files, from_files) 로 정렬해 반환한다(작성일 오름차순)."""
    data_dir = get_data_dir()
    until_files = sorted(data_dir.glob(f"until_*_{stock_name}_comment.jsonl"))
    from_files = sorted(data_dir.glob(f"from_*_{stock_name}_comment.jsonl"))
    return until_files, from_files


def _daily_counts_from_files(files):
    """파일 목록을 순회해 작성일(YYYYMMDD)별 총 댓글 수를 합산해 반환한다."""
    daily = {}
    for f in files:
        for date_key, n in comment_store.count_by_created_date(f).items():
            daily[date_key] = daily.get(date_key, 0) + n
    return daily


def _recent_id_from_files(until_files, from_files):
    """recent_comment_id 를 파일에서 도출한다.

    from_ 파일에 유효 댓글이 있으면 'from_ 파일 전체의 최댓값 commentId', 없으면
    'until_ 파일 전체의 최댓값 commentId'. 둘 다 없으면 None.
    (from_ 은 여러 실행분이 여러 파일에 흩어질 수 있으므로 파일별 max_comment_id 의
    전체 최댓값으로 구하고, from_ 이 비어 있으면 until_ 백필로 폴백한다.)
    """
    for files in (from_files, until_files):       # from_ 우선, 비면 until_ 폴백
        best = None
        for f in files:
            cid = comment_store.max_comment_id(f)             # 파일 전체 스캔 최댓값
            if cid is not None and (best is None or cid > best):
                best = cid
        if best is not None:
            return best
    return None


def recent_id_from_files(stock_name):
    """종목의 수집 파일에서 recent_id(증분 경계)를 도출한다(init_manifest·증분 seed 공용).

    from_ 있으면 from_ 전체 최댓값, 없으면 until_ 전체 최댓값, 둘 다 없으면 None.
    두 경로가 같은 규칙을 쓰도록 rebuild_from_files 와 _seed_recent_boundary 가 공유한다.
    """
    until_files, from_files = _stock_files(stock_name)
    return _recent_id_from_files(until_files, from_files)


def rebuild_from_files(stock_name, subject_id, extra_modes=None):
    """(배치) 종목의 모든 until_/from_ 파일을 스캔해 매니페스트를 재작성한다(멱등).

    - daily_counts: until+from 전체의 작성일별 총 댓글 수(절대값 덮어쓰기)
    - modes.incremental.recent_id: from_ 있으면 from_ 전체 최댓값, 없으면 until_ 전체
      최댓값(_recent_id_from_files). from_·until_ 둘 다 유효 댓글이 없으면 기록 안 함.
    - extra_modes: {mode: {필드}} 를 modes 에 병합(예: backfill 레거시 상태 이관)
    """
    until_files, from_files = _stock_files(stock_name)
    daily = _daily_counts_from_files(until_files + from_files)

    modes = {}
    recent_id = _recent_id_from_files(until_files, from_files)
    if recent_id is not None:              # from_ 이든 until_ 이든 최댓값이 나오면 경계로 기록
        modes["incremental"] = {
            "recent_id": recent_id,
            "source": "rebuilt_from_files",
        }
    if extra_modes:
        for mode, fields in extra_modes.items():
            modes.setdefault(mode, {}).update(fields)

    return rebuild(stock_name, subject_id, daily, mode_summaries=modes)


def update_from_files(stock_name, subject_id, result, out_files):
    """(증분) 이번 실행이 기록한 파일만 스캔해 매니페스트를 갱신한다(가벼운 버전).

    record_run 의 증분용 대체. 전 파일 스캔 대신 out_files(보통 오늘 1~2개)만 본다.
    - daily_counts: out_files 각 파일의 작성일별 '절대' 카운트로 그 날짜만 덮어씀(self-heal)
    - modes[result.mode]: 실행 요약(status/stop_reason/collected/pages/final_cursor) 병합
    - last_success_at: done 인 실행의 시각

    recent_id 는 여기서 쓰지 않는다. live 증분의 경계 기록자는 crawl_from_now 의
    pending_recent(시작 시점 최신 = 가장 정확, 자정 파티션 엣지에 안전, P0-1 반영) 하나뿐이다.
    (파일에서 recent_id 를 도출하는 것은 in-memory 경계가 없는 rebuild_from_files 전용.)
    """
    m = load(stock_name) or {"stock": stock_name, "subject_id": subject_id,
                             "modes": {}, "daily_counts": {}}
    now = datetime.now(KST).isoformat(timespec="seconds")
    m["subject_id"] = subject_id
    m["updated_at"] = now

    # 작성일별 파일이라 한 파일=한 날짜. 그 날짜 카운트를 파일의 절대값으로 덮어써 self-heal.
    daily = m.setdefault("daily_counts", {})
    for f in out_files:
        for date_key, n in comment_store.count_by_created_date(f).items():
            daily[date_key] = n

    mode_entry = m.setdefault("modes", {}).setdefault(result.mode, {})
    mode_entry.update({
        "last_run_at": now,
        "status": result.status,
        "stop_reason": result.stop_reason,
        "collected": result.collected,
        "pages": result.pages,
        "final_cursor": result.final_cursor,
    })

    # recent_id 는 crawl_from_now(pending_recent)가 done 에서만 이미 확정하므로 건드리지 않는다.
    if result.status == "done":
        m["last_success_at"] = now

    if daily:
        keys = sorted(daily)
        m["coverage"] = {"floor_date": keys[0], "latest_date": keys[-1]}

    atomic_write_json(_path(stock_name), m)
    return m
