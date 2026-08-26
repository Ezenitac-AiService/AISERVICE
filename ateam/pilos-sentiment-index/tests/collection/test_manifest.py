"""manifest.record_run 병합 로직 단위 테스트.

저장 경로(json_io.DATA_DIR)를 임시 디렉터리로 돌려 실제 data/raw 를 건드리지 않는다.

실행:  uv run python -m unittest discover -s tests/collection -p "test_manifest.py"
"""
import tempfile
import unittest
from pathlib import Path

from pilos.collection.comment_crawler import CrawlResult
from pilos.storage import comment_store, json_io, manifest

STOCK = "SK하이닉스"
SUBJECT = "KR7000660001"


def result(mode, status, stop_reason, collected, daily, cursor=100):
    return CrawlResult(STOCK, mode, pages=1, collected=collected, stop_reason=stop_reason,
                       status=status, final_cursor=cursor, elapsed_sec=0.1, daily_counts=daily)


class ManifestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._data_dir = json_io.DATA_DIR
        json_io.DATA_DIR = self.tmp
        self.addCleanup(setattr, json_io, "DATA_DIR", self._data_dir)

    def test_records_counts_coverage_and_success(self):
        m = manifest.record_run(STOCK, SUBJECT, result(
            "incremental", "done", "reached_recent", 3, {"20260728": 1, "20260729": 2}))
        self.assertEqual(m["daily_counts"], {"20260728": 1, "20260729": 2})
        self.assertEqual(m["coverage"], {"floor_date": "20260728", "latest_date": "20260729"})
        self.assertEqual(m["modes"]["incremental"]["status"], "done")
        self.assertIn("last_success_at", m)

    def test_daily_counts_accumulate_across_runs(self):
        manifest.record_run(STOCK, SUBJECT, result(
            "incremental", "done", "reached_recent", 2, {"20260729": 2}))
        m = manifest.record_run(STOCK, SUBJECT, result(
            "incremental", "done", "reached_recent", 3, {"20260729": 1, "20260730": 2}))
        self.assertEqual(m["daily_counts"], {"20260729": 3, "20260730": 2})   # 누적
        self.assertEqual(m["coverage"], {"floor_date": "20260729", "latest_date": "20260730"})

    def test_interrupted_does_not_set_success(self):
        m = manifest.record_run(STOCK, SUBJECT, result(
            "incremental", "interrupted", "fetch_failed", 1, {"20260729": 1}))
        self.assertEqual(m["modes"]["incremental"]["status"], "interrupted")
        self.assertNotIn("last_success_at", m)

    def test_two_modes_coexist(self):
        manifest.record_run(STOCK, SUBJECT, result("backfill", "done", "reached_date", 5, {"20260101": 5}))
        m = manifest.record_run(STOCK, SUBJECT, result("incremental", "done", "reached_recent", 2, {"20260729": 2}))
        self.assertIn("backfill", m["modes"])
        self.assertIn("incremental", m["modes"])
        self.assertEqual(m["coverage"], {"floor_date": "20260101", "latest_date": "20260729"})

    def test_find_coverage_gaps_reports_missing_days(self):
        m = manifest.record_run(STOCK, SUBJECT, result(
            "backfill", "done", "reached_date", 4, {"20260728": 2, "20260731": 2}))  # 29·30 없음
        self.assertEqual(manifest.find_coverage_gaps(m), ["20260729", "20260730"])

    def test_find_coverage_gaps_none_when_contiguous(self):
        m = manifest.record_run(STOCK, SUBJECT, result(
            "incremental", "done", "reached_recent", 3, {"20260728": 1, "20260729": 1, "20260730": 1}))
        self.assertEqual(manifest.find_coverage_gaps(m), [])

    def test_find_coverage_gaps_empty_manifest(self):
        self.assertEqual(manifest.find_coverage_gaps(None), [])
        self.assertEqual(manifest.find_coverage_gaps({}), [])


def _cmt(cid, date="20260729"):
    return {"commentId": cid, "createdAt": f"{date[:4]}-{date[4:6]}-{date[6:]}T00:00:00+09:00"}


class RebuildRecentIdTest(unittest.TestCase):
    """rebuild_from_files 가 recent_id 를 파일 종류별 전체 최댓값으로 세우는지 검증."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._data_dir = json_io.DATA_DIR
        json_io.DATA_DIR = self.tmp
        self.addCleanup(setattr, json_io, "DATA_DIR", self._data_dir)

    def _write_until(self, target_date, ids):
        comment_store.append_comments(json_io.get_comment_file(STOCK, target_date),
                                      [_cmt(i, target_date) for i in ids])

    def _write_from(self, created_date, ids):
        comment_store.append_comments(json_io.get_incremental_comment_file(STOCK, created_date),
                                      [_cmt(i, created_date) for i in ids])

    def test_until_only_recent_id_is_global_max(self):
        # 여러 until_ 파일에 흩어진 comment_id 의 전체 최댓값(첫 줄 아님)
        self._write_until("20260101", [100, 305, 200])
        self._write_until("20260601", [280, 260])
        m = manifest.rebuild_from_files(STOCK, SUBJECT)
        self.assertEqual(m["modes"]["incremental"]["recent_id"], 305)

    def test_from_present_uses_from_global_max_ignoring_until(self):
        # from_ 있으면 until_ 무시, from_ '전체' 최댓값(최신 날짜 파일만이 아님)
        self._write_until("20260101", [999])            # until 이 더 커도 무시
        self._write_from("20260728", [400, 420])        # 이른 날짜 파일에 전체 최댓값
        self._write_from("20260729", [410, 415])        # 최신 날짜 파일 max=415
        m = manifest.rebuild_from_files(STOCK, SUBJECT)
        self.assertEqual(m["modes"]["incremental"]["recent_id"], 420)

    def test_no_files_leaves_no_incremental_recent_id(self):
        m = manifest.rebuild_from_files(STOCK, SUBJECT)
        self.assertIsNone((m.get("modes", {}).get("incremental") or {}).get("recent_id"))


if __name__ == "__main__":
    unittest.main()
