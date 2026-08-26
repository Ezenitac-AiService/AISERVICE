"""crawl_until_date(백필) 단위 테스트.

네트워크(_fetch_comments)는 준비된 페이지로 대체하고, 저장 경로(json_io.DATA_DIR)는
임시 디렉터리로 돌려 실제 data/raw 를 건드리지 않는다. 표준 unittest 만 사용한다.

실행:  uv run python -m unittest discover -s tests/collection -p "test_crawl_backfill.py"
"""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from pilos.collection import comment_crawler as m
from pilos.collection.constants import KST
from pilos.storage import json_io, manifest

SUBJECT_ID = "KR7000660001"          # STOCK_NAME → "SK하이닉스"
STOCK = "SK하이닉스"
TARGET = datetime(2026, 6, 1, tzinfo=KST)


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


def stop_before_target(comment):
    """createdAt 이 TARGET 이전이면 종료(백필 stop_when)."""
    return datetime.fromisoformat(comment["createdAt"]) < TARGET


def fetch_returning(pages):
    """페이지를 순서대로 돌려주는 가짜 _fetch_comments(소진 시 빈 페이지)."""
    it = iter(pages)

    def _fetch(target_url, headers):
        try:
            return next(it)
        except StopIteration:
            return []
    return _fetch


class BackfillTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.out_file = self.tmp / "comments.jsonl"
        # 저장 경로를 임시로, 네트워크 대기를 제거
        self._data_dir = json_io.DATA_DIR
        json_io.DATA_DIR = self.tmp / "raw"
        self.addCleanup(setattr, json_io, "DATA_DIR", self._data_dir)
        p = mock.patch("time.sleep", lambda *a, **k: None)
        p.start()
        self.addCleanup(p.stop)

    def _saved_ids(self):
        if not self.out_file.exists():
            return []
        return [json.loads(line)["commentId"]
                for line in self.out_file.read_text(encoding="utf-8-sig").splitlines() if line.strip()]

    def _run(self, pages, stop_when=stop_before_target):
        stock_info = {"stock_subject_id": SUBJECT_ID, "stock_name": STOCK}
        with mock.patch.object(m, "_fetch_comments", fetch_returning(pages)):
            result, out_file = m.crawl_until_date(stock_info, self.out_file, stop_when)
            self._last_out_file = out_file   # 반환된 파일 Path 검증용으로 보관
            return result

    # ------------------------------------------------------------------
    def test_stops_at_date_saves_done(self):
        pages = [
            [cmt("10", "2026-07-10T00:00:00+09:00"), cmt("9", "2026-07-05T00:00:00+09:00")],
            [cmt("8", "2026-06-10T00:00:00+09:00"), cmt("7", "2026-05-20T00:00:00+09:00")],  # 7 < target → stop
        ]
        r = self._run(pages)
        self.assertEqual(self._saved_ids(), ["10", "9", "8"])   # 경계(7)는 저장 안 함
        self.assertEqual(r.collected, 3)
        self.assertEqual(r.stop_reason, m.STOP_REACHED_DATE)
        self.assertEqual(r.status, "done")
        self.assertEqual(manifest.load_backfill_status(STOCK), "done")
        self.assertEqual(manifest.load_backfill_cursor(STOCK), "7")   # 커서는 정지 지점

    def test_fetch_failure_interrupted(self):
        pages = [
            [cmt("10"), cmt("9")],
            None,                       # 재시도 후에도 실패
        ]
        r = self._run(pages)
        self.assertEqual(self._saved_ids(), ["10", "9"])
        self.assertEqual(r.stop_reason, m.STOP_FETCH_FAILED)
        self.assertEqual(r.status, "interrupted")
        self.assertEqual(manifest.load_backfill_status(STOCK), "interrupted")
        self.assertEqual(manifest.load_backfill_cursor(STOCK), "9")   # 재개 지점 보존

    def test_dedup_on_rerun(self):
        pages = [
            [cmt("10", "2026-07-10T00:00:00+09:00"), cmt("9", "2026-07-05T00:00:00+09:00")],
            [cmt("8", "2026-06-10T00:00:00+09:00"), cmt("7", "2026-05-20T00:00:00+09:00")],
        ]
        self._run(pages)
        first = self._saved_ids()
        r2 = self._run(pages)                       # 동일 페이지 재수집
        self.assertEqual(self._saved_ids(), first)  # 파일 변화 없음(중복 없음)
        self.assertEqual(r2.collected, 0)

    def test_missing_created_at_skipped_not_stopped(self):
        pages = [
            [cmt("10"), cmt("99", created=None), cmt("9")],   # 99는 createdAt 없음
            [cmt("7", "2026-05-20T00:00:00+09:00")],          # stop
        ]
        # createdAt None 이어도 stop 판정을 건너뛰고, 저장에서도 제외돼야 한다
        pages[0][1]["createdAt"] = None
        r = self._run(pages)
        self.assertNotIn("99", self._saved_ids())
        self.assertEqual(self._saved_ids(), ["10", "9"])
        self.assertEqual(r.status, "done")

    def test_returns_out_file_path(self):
        pages = [[cmt("10", "2026-07-10T00:00:00+09:00")], [cmt("7", "2026-05-20T00:00:00+09:00")]]
        self._run(pages)
        # 넘긴 대상 파일과 동일한 Path 를 돌려준다.
        self.assertEqual(self._last_out_file, self.out_file)


if __name__ == "__main__":
    unittest.main()
