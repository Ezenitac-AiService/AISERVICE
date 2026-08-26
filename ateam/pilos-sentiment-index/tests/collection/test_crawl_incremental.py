"""crawl_from_now(증분) 단위 테스트.

네트워크(_fetch_comments)는 준비된 페이지로 대체하고, 저장 경로(json_io.DATA_DIR)는
임시 디렉터리로 돌려 실제 data/raw 를 건드리지 않는다. 표준 unittest 만 사용한다.

핵심 검증: P0-1 — 최신 지점(recent_comment_id)은 '정상 종료 시에만' 확정 저장된다.

실행:  uv run python -m unittest discover -s tests/collection -p "test_crawl_incremental.py"
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pilos.collection import comment_crawler as m
from pilos.jobs import incremental_comments as runner
from pilos.storage import comment_store, json_io, manifest

SUBJECT_ID = "KR7000660001"          # STOCK_NAME → "SK하이닉스"
STOCK = "SK하이닉스"


def cmt(cid, created="2026-07-10T00:00:00+09:00", **extra):
    """테스트용 댓글 dict 를 만든다(익명화에 필요한 author 필드 포함)."""
    d = {
        "commentId": cid,
        "createdAt": created,
        "author": {"userProfileId": f"u{cid}", "nickname": f"n{cid}"},
        "authorUserProfileId": f"u{cid}",
    }
    d.update(extra)
    return d


def fetch_returning(pages):
    """페이지를 순서대로 돌려주는 가짜 _fetch_comments(소진 시 빈 페이지)."""
    it = iter(pages)

    def _fetch(target_url, headers):
        try:
            return next(it)
        except StopIteration:
            return []
    return _fetch


class IncrementalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._data_dir = json_io.DATA_DIR
        json_io.DATA_DIR = self.tmp / "raw"
        self.addCleanup(setattr, json_io, "DATA_DIR", self._data_dir)
        p = mock.patch("time.sleep", lambda *a, **k: None)
        p.start()
        self.addCleanup(p.stop)

    def _saved_ids(self):
        # createdAt 날짜별 from_*_SK하이닉스_comment.jsonl 을 날짜 오름차순으로 합쳐 읽는다.
        ids = []
        for f in sorted(json_io.DATA_DIR.glob(f"from_*_{STOCK}_comment.jsonl")):
            ids += [json.loads(line)["commentId"]
                    for line in f.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        return ids

    def _run(self, pages):
        def out_file_for(date_key, _name=STOCK):
            return json_io.get_incremental_comment_file(_name, date_key)
        stock_info = {"stock_subject_id": SUBJECT_ID, "stock_name": STOCK}
        with mock.patch.object(m, "_fetch_comments", fetch_returning(pages)):
            self._last_out_files = None
            result, out_files = m.crawl_from_now(stock_info, out_file_for)
            self._last_out_files = out_files   # 반환된 파일 Path 목록 검증용으로 보관
            return result

    # ------------------------------------------------------------------
    def test_stops_at_recent_and_saves_recent(self):
        manifest.save_recent_id(STOCK, "5")   # 직전 실행 최신 지점
        pages = [
            [cmt("8"), cmt("7")],
            [cmt("6"), cmt("5")],       # 5 == end_before → stop
        ]
        r = self._run(pages)
        self.assertEqual(self._saved_ids(), ["8", "7", "6"])    # 경계(5)는 저장 안 함
        self.assertEqual(r.stop_reason, m.STOP_REACHED_RECENT)
        self.assertEqual(r.status, "done")
        self.assertEqual(manifest.load_recent_id(STOCK), "8")   # 이번 최신 확정

    def test_fetch_failure_keeps_old_recent(self):
        """P0-1: 실패 시 recent 를 앞당기지 않아 유실 구간이 생기지 않는다."""
        manifest.save_recent_id(STOCK, "5")
        pages = [
            [cmt("8"), cmt("7")],
            None,                       # 수집 중 실패
        ]
        r = self._run(pages)
        self.assertEqual(self._saved_ids(), ["8", "7"])
        self.assertEqual(r.stop_reason, m.STOP_FETCH_FAILED)
        self.assertEqual(r.status, "interrupted")
        self.assertEqual(manifest.load_recent_id(STOCK), "5")   # 그대로 5 (8로 안 앞당김)

    def test_first_run_no_recent_until_empty(self):
        pages = [
            [cmt("8"), cmt("7")],
            [cmt("6")],
            [],                         # 더 없음 → 자연 종료
        ]
        r = self._run(pages)
        self.assertEqual(self._saved_ids(), ["8", "7", "6"])
        self.assertEqual(r.stop_reason, m.STOP_EMPTY)
        self.assertEqual(r.status, "done")
        self.assertEqual(manifest.load_recent_id(STOCK), "8")

    def test_dedup_on_rerun(self):
        manifest.save_recent_id(STOCK, "5")
        pages = [[cmt("8"), cmt("7")], [cmt("6"), cmt("5")]]
        self._run(pages)
        r2 = self._run(pages)           # recent 가 8이 되어 즉시 종료
        self.assertEqual(r2.collected, 0)
        self.assertEqual(self._saved_ids(), ["8", "7", "6"])

    def test_rerun_after_failure_resumes_no_gap(self):
        """§4-4: 실패로 경계가 앞당겨지지 않아, 재실행이 이전 경계부터 누락·중복 없이 이어받는다."""
        manifest.save_recent_id(STOCK, "5")
        # 1차: 8,7 을 저장한 뒤 수집 중 실패(None). 경계는 5 그대로 유지되어야 한다.
        r1 = self._run([[cmt("8"), cmt("7")], None])
        self.assertEqual(r1.status, "interrupted")
        self.assertEqual(manifest.load_recent_id(STOCK), "5")   # 8 로 앞당기지 않음
        self.assertEqual(self._saved_ids(), ["8", "7"])
        # 2차 재실행: 경계 5부터 다시. 9,6 은 신규, 8·7 은 파일 dedup 으로 재적재 안 됨.
        r2 = self._run([[cmt("9"), cmt("8")], [cmt("7"), cmt("6")], [cmt("5")]])
        self.assertEqual(r2.status, "done")
        self.assertEqual(r2.stop_reason, m.STOP_REACHED_RECENT)
        self.assertEqual(r2.collected, 2)                        # 9,6 만 신규(8,7 은 중복 제외)
        self.assertEqual(self._saved_ids(), ["8", "7", "9", "6"])  # 누락(6,7,8,9 모두 존재)·중복 없음
        self.assertEqual(manifest.load_recent_id(STOCK), "9")   # 정상 종료라 경계 확정

    def test_returns_written_file_paths(self):
        manifest.save_recent_id(STOCK, "5")
        pages = [
            [cmt("8", "2026-07-10T00:00:00+09:00"), cmt("7", "2026-07-11T00:00:00+09:00")],
            [cmt("5")],                 # 5 == end_before → stop (저장 안 함)
        ]
        self._run(pages)
        # 작성일이 다른 8·7 → 두 개의 날짜 파일이 만들어지고 그 Path 들이 반환된다.
        self.assertEqual(
            sorted(p.name for p in self._last_out_files),
            sorted([json_io.get_incremental_comment_file(STOCK, "20260710").name,
                    json_io.get_incremental_comment_file(STOCK, "20260711").name]),
        )


class SeedRecentBoundaryTest(unittest.TestCase):
    """첫 증분 실행 시 경계(recent_comment_id)를 from_ 최신(없으면 백필)으로 세우는지 검증."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._data_dir = json_io.DATA_DIR
        json_io.DATA_DIR = self.tmp
        self.addCleanup(setattr, json_io, "DATA_DIR", self._data_dir)

    def _write_backfill(self, target_date, ids):
        # 백필은 최신→과거 순 append → 첫 id 가 최신.
        comment_store.append_comments(json_io.get_comment_file(STOCK, target_date),
                                      [cmt(i) for i in ids])

    def _write_from(self, created_date, ids):
        # 증분 결과 from_ 파일. 여러 실행분이 이어 붙어 첫 줄이 최신이 아닐 수 있다.
        comment_store.append_comments(
            json_io.get_incremental_comment_file(STOCK, created_date),
            [cmt(i) for i in ids],
        )

    def test_seed_uses_backfill_newest_when_missing(self):
        self._write_backfill("20260601", ["300", "299", "298"])
        runner._seed_recent_boundary(STOCK)
        self.assertEqual(manifest.load_recent_id(STOCK), "300")   # 첫 줄=최신

    def test_seed_uses_from_max_when_present(self):
        # 첫 줄("298")이 최신이 아니고 전체 최댓값("305")을 경계로 삼아야 한다.
        self._write_from("20260710", ["298", "305", "301"])
        runner._seed_recent_boundary(STOCK)
        self.assertEqual(manifest.load_recent_id(STOCK), "305")

    def test_seed_prefers_latest_from_file_over_backfill(self):
        # from_ 최신 파일(작성일 20260711)의 최댓값이 백필보다 우선한다.
        self._write_backfill("20260601", ["300"])
        self._write_from("20260710", ["310"])
        self._write_from("20260711", ["320", "315"])
        runner._seed_recent_boundary(STOCK)
        self.assertEqual(manifest.load_recent_id(STOCK), "320")

    def test_seed_falls_back_to_backfill_when_from_empty(self):
        # from_ 파일이 존재하지만 유효 댓글이 없으면 백필로 폴백한다.
        json_io.get_incremental_comment_file(STOCK, "20260710").write_text(
            "\n", encoding="utf-8"
        )
        self._write_backfill("20260601", ["300"])
        runner._seed_recent_boundary(STOCK)
        self.assertEqual(manifest.load_recent_id(STOCK), "300")

    def test_seed_noop_when_recent_exists(self):
        manifest.save_recent_id(STOCK, "999")
        self._write_from("20260710", ["320"])
        runner._seed_recent_boundary(STOCK)
        self.assertEqual(manifest.load_recent_id(STOCK), "999")   # 기존 경계 유지

    def test_seed_noop_when_no_files(self):
        runner._seed_recent_boundary(STOCK)
        self.assertIsNone(manifest.load_recent_id(STOCK))         # 세울 근거 없음


if __name__ == "__main__":
    unittest.main()
