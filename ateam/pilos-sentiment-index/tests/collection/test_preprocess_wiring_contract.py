"""수집→전처리 배선 계약 테스트(§4-6·4-7·4-10).

실제 DB·전처리 내부 계산 없이, 배선 계약만 확인한다.
- §4-6 같은 날짜 파일에 append 된 신규 행(watermark 이후)만 전처리 대상으로 선택된다.
- §4-7 수집이 반환한 과거 작성일 파일도 오늘 필터에 걸리지 않고 전처리로 전달된다.
- §4-10 전처리 파일 부분 실패가 최상위 호출자에게 요약으로 반환된다.

실행:  uv run python -m unittest discover -s tests/collection -p "test_preprocess_wiring_contract.py"
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pilos.jobs.preprocess_comments as tp
from pilos.storage.jsonl import iter_jsonl_records


class WatermarkSelectionTest(unittest.TestCase):
    """§4-6: watermark(start_after_line) 이후 새 줄만 파싱·선택된다."""

    def _write_jsonl(self, n):
        path = Path(tempfile.mkdtemp()) / "from_20260810_종목_comment.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for i in range(1, n + 1):
                f.write(json.dumps({"commentId": str(i)}, ensure_ascii=False) + "\n")
        return path

    def test_skips_up_to_watermark(self):
        path = self._write_jsonl(5)
        recs = list(iter_jsonl_records(path, start_after_line=3))
        # 4,5 줄(=append 된 신규 행)만 선택된다.
        self.assertEqual([r["commentId"] for r in recs], ["4", "5"])
        # 물리적 줄 번호가 raw_line_number 로 보존된다(다음 watermark 계산 근거).
        self.assertEqual([r["raw_line_number"] for r in recs], [4, 5])

    def test_watermark_zero_reads_all(self):
        path = self._write_jsonl(5)
        recs = list(iter_jsonl_records(path, start_after_line=0))
        self.assertEqual(len(recs), 5)


class RecordedFilesWiringTest(unittest.TestCase):
    """§4-7·4-10: 수집이 반환한 파일 목록을 그대로 전처리 대상으로 넘기는 배선."""

    def test_past_dated_file_is_passed_through(self):
        # 과거 작성일(0731) 파일도 '오늘 날짜' 필터에 누락되지 않고 조회·전처리된다(§4-7).
        recorded = [
            Path("raw/from_20260731_SK하이닉스_comment.jsonl"),   # 지연 댓글(과거 작성일)
            Path("raw/from_20260810_SK하이닉스_comment.jsonl"),   # 오늘분
        ]
        looked_up = []

        def fake_select(name):
            looked_up.append(name)
            return {"file_name": name}

        with mock.patch.object(tp, "select_source_file_by_name", side_effect=fake_select), \
             mock.patch.object(tp, "preprocess_one_source_file", return_value=2) as pp:
            summary = tp.run_preprocessing_for_files(recorded)

        self.assertIn("from_20260731_SK하이닉스_comment", looked_up)  # 과거 파일도 조회됨
        self.assertEqual(summary.total, 2)
        self.assertEqual(summary.inserted, 4)     # 파일당 2건씩
        self.assertEqual(summary.failed, 0)
        self.assertEqual(pp.call_count, 2)

    def test_partial_failure_is_returned_to_caller(self):
        # 미등록 파일과 전처리 예외 파일이 섞여도, 정상 파일은 적재하고 실패는 요약에 남긴다(§4-10).
        recorded = [
            Path("raw/from_20260810_A_comment.jsonl"),   # source_comment_file 미등록
            Path("raw/from_20260810_B_comment.jsonl"),   # 전처리 중 예외
            Path("raw/from_20260810_C_comment.jsonl"),   # 정상
        ]

        def fake_select(name):
            return None if name.endswith("_A_comment") else {"file_name": name}

        def fake_pp(source_file):
            if source_file["file_name"].endswith("_B_comment"):
                raise RuntimeError("preprocess boom")
            return 5

        with mock.patch.object(tp, "select_source_file_by_name", side_effect=fake_select), \
             mock.patch.object(tp, "preprocess_one_source_file", side_effect=fake_pp):
            summary = tp.run_preprocessing_for_files(recorded)

        self.assertEqual(summary.total, 3)
        self.assertEqual(summary.inserted, 5)     # C 만 성공
        self.assertEqual(summary.failed, 2)       # A(미등록) + B(예외)
        self.assertEqual(
            set(summary.failed_files),
            {"from_20260810_A_comment", "from_20260810_B_comment"},
        )


if __name__ == "__main__":
    unittest.main()
