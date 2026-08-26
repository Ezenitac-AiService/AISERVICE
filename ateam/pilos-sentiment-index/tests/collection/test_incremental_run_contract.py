"""증분 실행기(run_incremental/main)의 실행 계약 테스트(§4 검증).

네트워크·실제 DB 없이, require_connection 과 crawl_from_now 를 대체해 실행기 조합
계약만 확인한다. manifest 저장은 임시 디렉터리로 돌린다.

검증 항목:
- §4-1 sk/others 가 각 실행함수 호출에서 올바르게 분리된다.
- §4-2 DB 초기화 실패가 정의된 실패 결과(CommentDBUnavailableError → 종료코드 1)로 처리된다.
- §4-9 일부 종목 실패가 전체 결과에 부분 실패로 나타난다.

실행:  uv run python -m unittest discover -s tests/collection -p "test_incremental_run_contract.py"
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pilos.collection.comment_crawler import STOP_EMPTY, CrawlResult
from pilos.collection.constants import SK_HYNIX_ID
from pilos.jobs import backfill_comments as bf
from pilos.jobs import incremental_comments as inc
from pilos.storage import json_io
from pilos.storage.comment_db import CommentDBUnavailableError

# 테스트용 종목 행: (stock_id, 종목명, subjectId). SK 1건 + 그 외 2건.
_SK = ("1", "SK하이닉스", SK_HYNIX_ID)
_A = ("2", "삼성전자", "SUBJ_A")
_B = ("3", "현대차", "SUBJ_B")
_TARGETS = [_SK, _A, _B]


class FilterTargetsTest(unittest.TestCase):
    """§4-1: target 선택이 sk/others/전체로 올바르게 분리된다(두 실행기 동일 계약)."""

    def _check(self, filter_targets):
        self.assertEqual(filter_targets(_TARGETS, "sk"), [_SK])
        self.assertEqual(filter_targets(_TARGETS, "others"), [_A, _B])
        self.assertEqual(filter_targets(_TARGETS, None), _TARGETS)

    def test_incremental_filter(self):
        self._check(inc._filter_targets)

    def test_backfill_filter(self):
        self._check(bf._filter_targets)


class DBUnavailableContractTest(unittest.TestCase):
    """§4-2: DB 초기화 실패는 조용한 AttributeError 가 아니라 정의된 실패로 처리된다."""

    def test_run_incremental_propagates_db_error(self):
        with mock.patch.object(
            inc, "require_connection", side_effect=CommentDBUnavailableError("no db")
        ):
            with self.assertRaises(CommentDBUnavailableError):
                inc.run_incremental(target="sk")

    def test_incremental_main_converts_db_error_to_exit_1(self):
        with mock.patch.object(
            inc, "require_connection", side_effect=CommentDBUnavailableError("no db")
        ), mock.patch.object(inc, "setup_logging"):
            self.assertEqual(inc.main(target="sk"), 1)

    def test_backfill_main_converts_db_error_to_exit_1(self):
        with mock.patch.object(
            bf, "require_connection", side_effect=CommentDBUnavailableError("no db")
        ), mock.patch.object(bf, "setup_logging"):
            self.assertEqual(bf.main(target="sk"), 1)


class _FakeDB:
    """select_stock/insert_source 만 흉내내는 DB 대체(네트워크·실제 DB 없음)."""

    def __init__(self, stocks):
        self._stocks = stocks
        self.inserted = []

    def select_stock(self):
        return self._stocks

    def insert_source(self, file_source):
        self.inserted.append(file_source)
        return 1


class PartialFailureTest(unittest.TestCase):
    """§4-9: 한 종목이 실패해도 나머지는 계속하고, 요약에 부분 실패가 나타난다."""

    def setUp(self):
        # manifest 저장 경로를 임시로 돌린다(실제 data/raw 를 건드리지 않음).
        self._data_dir = json_io.DATA_DIR
        json_io.DATA_DIR = Path(tempfile.mkdtemp()) / "raw"
        self.addCleanup(setattr, json_io, "DATA_DIR", self._data_dir)

    def test_one_stock_exception_is_partial_failure(self):
        fake_db = _FakeDB([_A, _B])   # target=None → 두 종목 모두

        def fake_crawl(stock_info, out_file_for):
            # 현대차(_B)만 크롤링 중 예외. 삼성(_A)은 정상 종료.
            if stock_info["stock_name"] == _B[1]:
                raise RuntimeError("crawl boom")
            result = CrawlResult(
                stock_info["stock_name"], "incremental", 1, 3, STOP_EMPTY, "done", None, 0.1, {}
            )
            return result, []   # 기록 파일 없음(insert_source 루프 건너뜀)

        with mock.patch.object(inc, "require_connection", return_value=fake_db), \
             mock.patch.object(inc, "crawl_from_now", side_effect=fake_crawl):
            summary = inc.run_incremental(target=None)

        self.assertEqual(summary.total, 2)
        self.assertEqual(summary.succeeded, 1)
        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.exit_code, 1)               # 부분 실패 → 종료코드 1
        self.assertIn(f"{_B[1]}=exception", summary.failures)
        self.assertEqual(summary.collected, 3)               # 성공 종목 수집분만 집계
        statuses = {s.stock_name: s.status for s in summary.stocks}
        self.assertEqual(statuses[_A[1]], "done")
        self.assertEqual(statuses[_B[1]], "exception")


if __name__ == "__main__":
    unittest.main()
