import unittest
from datetime import date, time
from unittest.mock import MagicMock, patch

from pilos.storage.daily_document_db import (
    select_pending_daily_document_targets,
    select_tokenized_comments_for_day,
    insert_daily_document_with_comments,
)


class DailyDocumentTargetSelectionTest(unittest.TestCase):
    """일별 문서 대상 조회(select_pending_daily_document_targets) 계약 및 로직 검증."""

    def test_empty_tokenizer_version_raises_value_error(self):
        with self.assertRaises(ValueError):
            select_pending_daily_document_targets(
                tokenizer_version="",
                market_close_time=time(15, 30),
            )

    @patch("pilos.storage.daily_document_db.get_engine")
    def test_query_includes_stocks_with_unmapped_tokens_even_if_daily_document_exists(self, mock_get_engine):
        """기존 daily_document가 이미 존재하더라도, 미매핑 신규 토큰이 남아있으면 대상을 정상 반환해야 한다."""
        mock_conn = MagicMock()
        mock_get_engine.return_value.connect.return_value.__enter__.return_value = mock_conn

        # Mock result returning stock_id=1, model_date=2026-08-19
        mock_result = MagicMock()
        mock_result.mappings.return_value = [
            {"stock_id": 1, "model_date": date(2026, 8, 19)},
            {"stock_id": 2, "model_date": date(2026, 8, 20)},
        ]
        mock_conn.execute.return_value = mock_result

        targets = select_pending_daily_document_targets(
            tokenizer_version="kiwi_ver1",
            market_close_time=time(15, 30),
        )

        self.assertEqual(len(targets), 2)
        self.assertEqual(targets[0]["stock_id"], 1)
        self.assertEqual(targets[0]["model_date"], date(2026, 8, 19))
        self.assertEqual(targets[1]["stock_id"], 2)
        self.assertEqual(targets[1]["model_date"], date(2026, 8, 20))

        # Check SQL executed does not block existing daily_document
        executed_sql = str(mock_conn.execute.call_args[0][0])
        self.assertNotIn("NOT EXISTS (\n              SELECT 1\n              FROM daily_document AS dd", executed_sql)
        self.assertNotIn("FROM daily_document AS dd", executed_sql)


class DailyDocumentInsertionTest(unittest.TestCase):
    """일별 문서 스냅샷 생성 및 매핑 적재 계약 검증."""

    @patch("pilos.storage.daily_document_db.get_engine")
    def test_insert_reuses_existing_id_when_document_hash_matches(self, mock_get_engine):
        """동일한 document_hash가 이미 존재하면 새로 INSERT하지 않고 기존 daily_document_id를 반환한다 (Idempotency)."""
        mock_conn = MagicMock()
        mock_get_engine.return_value.begin.return_value.__enter__.return_value = mock_conn

        # Mock existing daily_document_id = 999
        mock_conn.execute.return_value.scalar.return_value = 999

        daily_document_data = {
            "stock_id": 1,
            "model_date": date(2026, 8, 19),
            "tokenizer_version": "kiwi_ver1",
            "tfidf_text": "반도체 상승 실적",
            "comment_count": 2,
            "document_hash": "a" * 64,
        }
        mapping_records = [
            {"tokenized_comment_id": 101, "sequence_number": 1},
            {"tokenized_comment_id": 102, "sequence_number": 2},
        ]

        result_id = insert_daily_document_with_comments(
            daily_document_data=daily_document_data,
            mapping_records=mapping_records,
        )

        self.assertEqual(result_id, 999)

    @patch("pilos.storage.daily_document_db.get_engine")
    def test_insert_creates_new_document_and_mappings_when_new_hash(self, mock_get_engine):
        """새로운 document_hash인 경우 새 daily_document_id를 생성하고 매핑을 적재한다."""
        mock_conn = MagicMock()
        mock_get_engine.return_value.begin.return_value.__enter__.return_value = mock_conn

        # Mock no existing id
        mock_conn.execute.return_value.scalar.return_value = None
        # Mock lastrowid = 1000
        mock_insert_result = MagicMock()
        mock_insert_result.lastrowid = 1000
        mock_mapping_result = MagicMock()
        mock_mapping_result.rowcount = 2

        mock_conn.execute.side_effect = [
            MagicMock(scalar=lambda: None), # SELECT existing
            mock_insert_result,             # INSERT daily_document
            mock_mapping_result,            # INSERT daily_document_comment
        ]

        daily_document_data = {
            "stock_id": 1,
            "model_date": date(2026, 8, 19),
            "tokenizer_version": "kiwi_ver1",
            "tfidf_text": "반도체 상승 실적 호조",
            "comment_count": 2,
            "document_hash": "b" * 64,
        }
        mapping_records = [
            {"tokenized_comment_id": 101, "sequence_number": 1},
            {"tokenized_comment_id": 103, "sequence_number": 2},
        ]

        result_id = insert_daily_document_with_comments(
            daily_document_data=daily_document_data,
            mapping_records=mapping_records,
        )

        self.assertEqual(result_id, 1000)


if __name__ == "__main__":
    unittest.main()
