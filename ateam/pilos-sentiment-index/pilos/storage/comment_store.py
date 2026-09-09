"""토스 댓글 원본(JSONL)의 저장·조회 (storage 계층).

collection 은 수집만 담당하고, 원본 JSONL 의 읽기/쓰기는 이 모듈이 담당한다
(D-001: 저장 책임은 storage). 원본 보존(DATA_CONTRACT §4): 필드명·시각·종목코드를
변형하지 않고 외부 응답 그대로 저장한다. 원본에는 중복이 존재할 수 있으며(§9),
comment_id 기준 중복 제거는 전처리 단계의 책임이다.
"""
import json
from collections import defaultdict, deque
from pathlib import Path


#====================================================
# 이거 수정할 것 좀 있을 것 같기도 해, 왜냐하면 자료형이 큐거든.... 이런...
#====================================================
def load_seen_comment_ids(out_file: Path, window: int = 2000) -> set:
    """out_file(JSONL) 꼬리 window 줄에서 commentId 집합을 읽어 반환한다(P2-1)."""
    seen = set()
    if not out_file.exists():
        return seen
    with open(out_file, mode="r", encoding="utf-8-sig") as f:
        # deque(maxlen)로 마지막 window 줄만 유지 → 비싼 json.loads 를 window 번만 수행
        for line in deque(f, maxlen=window):
            line = line.strip()
            if not line:
                continue
            try:
                seen.add(json.loads(line)["commentId"])
            except (json.JSONDecodeError, KeyError):
                continue
    return seen


#====================================================
# 파일 전체에서 가장 큰(=최신) commentId
#====================================================
def max_comment_id(out_file: Path):
    """JSONL 전체를 스캔해 가장 큰(=최신) commentId 를 반환한다(없으면 None).

    from_ 파일은 여러 증분 실행분이 이어 붙어 첫 줄이 최신이 아닐 수 있으므로,
    최신 경계(recent_id)는 첫 줄이 아니라 전체 최댓값으로 구해야 한다.
    """
    if not out_file.exists():
        return None
    best = None
    with open(out_file, mode="r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                cid = json.loads(line)["commentId"]
            except (json.JSONDecodeError, KeyError):
                continue
            if best is None or cid > best:
                best = cid
    return best




#====================================================
# 이거 솔직히 있어야하는지 모르것음
# 오류 안날 자신 있으면 없앨 수 있긴해
#====================================================
def seal_trailing_newline(out_file: Path) -> None:
    """마지막 바이트가 개행이 아니면 개행을 덧붙여 잘린 줄을 격리한다(P1-3)."""
    if not out_file.exists() or out_file.stat().st_size == 0:
        return
    with open(out_file, mode="rb") as f:
        f.seek(-1, 2)          # 파일 끝에서 1바이트 앞
        last_byte = f.read(1)
    if last_byte != b"\n":
        with open(out_file, mode="a", encoding="utf-8") as f:
            f.write("\n")      # 잘린 줄을 봉인해 다음 레코드와 분리


#====================================================
# 리스트를 통째로 jsonl으로 기록해버리는 함수
# 원래 만들었던 건 한 줄씩 기록하는 거였는데 이렇게 바뀜
# 모듈화하고 어쩌고 저쩌고 하면서 좀 복잡해졌음
#====================================================
def append_comments(out_file: Path, comments: list) -> None:
    """comment dict 목록을 out_file 에 JSONL 한 줄씩 append 한다(비었으면 no-op)."""
    if not comments:
        return
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, mode="a", encoding="utf-8") as f:
        f.writelines(json.dumps(comment, ensure_ascii=False, default=str) + "\n" for comment in comments)

#====================================================
# 날짜별로 댓글 모아둘 생각이었어서 만들긴 함
# 근데 굳이 이것도 함수로 만들었어야 했는지는 생각 생각해봄
#====================================================
def created_date_key(comment: dict) -> str:
    """댓글 createdAt 에서 'YYYYMMDD' 날짜 키를 뽑는다(예: 2026-07-10T...→20260710)."""
    return comment["createdAt"][:10].replace("-", "")


#====================================================
# 이렇게 저장해야 나중에 더 좋다고 해서 이렇게 해봄
# 근더 이거 볼 사람 있을까?
# 아무튼 메타데이터같은 느낌 있음
#====================================================
def count_by_created_date(out_file: Path) -> dict:
    """JSONL 파일을 스캔해 createdAt 날짜(YYYYMMDD)별 유효 레코드 수를 센다.

    손상/빈 줄과 createdAt 없는 레코드는 건너뛴다(매니페스트 초기화용).
    """
    counts = {}
    if not out_file.exists():
        return counts
    with open(out_file, mode="r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                created = json.loads(line)["createdAt"]
            except (json.JSONDecodeError, KeyError):
                continue
            if not created:
                continue
            key = created[:10].replace("-", "")
            counts[key] = counts.get(key, 0) + 1
    return counts


#====================================================
# 
#====================================================
class DatePartitionedAppender:
    """댓글을 createdAt 날짜별 파일로 라우팅해 append 한다(파일별 개행봉인·꼬리 dedup 포함).

    out_file_for : callable(date_key 'YYYYMMDD', _name=stock_name) -> Path
                   날짜 키와 종목명(_name 키워드)을 받아 저장 파일 경로를 돌려준다.
    stock_name   : 종목명. 매 append 마다 out_file_for 의 _name 인자로 전달된다.
    처음 만지는 날짜 파일만 봉인·dedup 셋을 lazy 로드하므로 비용이 만진 날짜 수에 비례한다.
    """

    def __init__(self, out_file_for, stock_name):
        self._out_file_for = out_file_for
        self.stock_name = stock_name
        self._seen = {}          # date_key -> set(commentId) (해당 날짜 파일에서 lazy 로드)
        self.written = {}        # date_key -> 실제로 기록한 건수(누적)

    def _seen_for(self, key: str) -> set:
        if key not in self._seen:
            path = self._out_file_for(key, _name = self.stock_name)
            seal_trailing_newline(path)              # 파일별 잘린 줄 봉인(P1-3)
            self._seen[key] = load_seen_comment_ids(path)  # 파일별 꼬리 dedup(P2-1)
        return self._seen[key]

    def written_paths(self) -> list[Path]:
        """실제로 기록한 날짜 파일들의 Path 목록을 작성일(YYYYMMDD) 오름차순으로 반환한다."""
        return [self._out_file_for(key, _name=self.stock_name) for key in sorted(self.written)]

    def append(self, comments: list) -> int:
        """comments 를 createdAt 날짜별로 나눠 append 하고, 실제로 기록한 건수를 반환한다."""
        buckets = defaultdict(list)
        for comment in comments:
            key = created_date_key(comment)
            seen = self._seen_for(key)
            cid = comment.get("commentId")
            if cid in seen:
                continue
            seen.add(cid)
            buckets[key].append(comment)
        written = 0
        for key, group in buckets.items():
            append_comments(self._out_file_for(key, _name = self.stock_name), group)
            self.written[key] = self.written.get(key, 0) + len(group)
            written += len(group)
        return written
