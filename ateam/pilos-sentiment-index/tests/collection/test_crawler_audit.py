import os
import unittest
from unittest.mock import MagicMock, patch

from pilos.collection import comment_crawler, data_masking
from pilos.collection.data_masking import anonymize_nickname, anonymize_user_profile_id


class TestCrawlerAudit(unittest.TestCase):
    def setUp(self):
        # Set dummy salts if not present for test execution
        if not data_masking.SECRET_SALT:
            data_masking.SECRET_SALT = "test_salt_1"
        if not data_masking.SECRET_SALT2:
            data_masking.SECRET_SALT2 = "test_salt_2"

    def test_data_masking_none_fallback(self):
        """None or empty profile ID and nickname must use default fallbacks without crashing."""
        anon_nick_none = anonymize_nickname(None)
        anon_nick_empty = anonymize_nickname("   ")
        anon_nick_real = anonymize_nickname("익명")
        self.assertEqual(anon_nick_none, anon_nick_real)
        self.assertEqual(anon_nick_empty, anon_nick_real)

        anon_prof_none = anonymize_user_profile_id(None)
        anon_prof_real = anonymize_user_profile_id("ANONYMOUS_USER")
        self.assertEqual(anon_prof_none, anon_prof_real)

    def test_select_page_missing_author_fields_preserved(self):
        """Comments without authorUserProfileId or nickname must NOT be dropped."""
        mock_comments = [
            {
                "commentId": 1001,
                "createdAt": "2026-08-19T10:00:00+09:00",
                "content": "정상 댓글",
                "author": {"userProfileId": "user_1", "nickname": "개미1"},
                "authorUserProfileId": "user_1"
            },
            {
                "commentId": 1002,
                "createdAt": "2026-08-19T10:01:00+09:00",
                "content": "프로필ID 누락 댓글",
                "author": {"nickname": "개미2"},  # userProfileId missing
                # authorUserProfileId missing
            },
            {
                "commentId": 1003,
                "createdAt": "2026-08-19T10:02:00+09:00",
                "content": "작성자 객체 전체 누락 댓글",
                # author is missing
            }
        ]

        seen_ids = set()
        should_stop = lambda c: False

        last_cursor, stopped, new_comments = comment_crawler._select_page(
            mock_comments, seen_ids, should_stop
        )

        self.assertFalse(stopped)
        self.assertEqual(last_cursor, 1003)
        self.assertEqual(len(new_comments), 3, "모든 유효 댓글(3건)이 보존되어야 함")
        self.assertEqual(new_comments[0]["commentId"], 1001)
        self.assertEqual(new_comments[1]["commentId"], 1002)
        self.assertEqual(new_comments[2]["commentId"], 1003)

    def test_select_page_nested_sub_comments_flattening(self):
        """Nested sub-comments/replies must be flattened into independent comment records."""
        mock_comments = [
            {
                "commentId": 2001,
                "createdAt": "2026-08-19T11:00:00+09:00",
                "content": "부모 댓글",
                "author": {"userProfileId": "user_p", "nickname": "부모"},
                "authorUserProfileId": "user_p",
                "replies": [
                    {
                        "commentId": 2002,
                        "createdAt": "2026-08-19T11:05:00+09:00",
                        "content": "대댓글 1",
                        "author": {"userProfileId": "user_c1", "nickname": "자식1"},
                        "authorUserProfileId": "user_c1"
                    },
                    {
                        "commentId": 2003,
                        "createdAt": "2026-08-19T11:06:00+09:00",
                        "content": "대댓글 2",
                        "author": {"userProfileId": "user_c2", "nickname": "자식2"}
                    }
                ]
            }
        ]

        seen_ids = set()
        should_stop = lambda c: False

        last_cursor, stopped, new_comments = comment_crawler._select_page(
            mock_comments, seen_ids, should_stop
        )

        self.assertFalse(stopped)
        self.assertEqual(len(new_comments), 3, "부모 1건 + 대댓글 2건 = 총 3건이어야 함")
        comment_ids = [c["commentId"] for c in new_comments]
        self.assertIn(2001, comment_ids)
        self.assertIn(2002, comment_ids)
        self.assertIn(2003, comment_ids)

    def test_backfill_target_filtering(self):
        """_filter_targets must correctly filter 'sk', 'others', and 'all'."""
        from pilos.jobs.backfill_comments import _filter_targets
        from pilos.collection.constants import SK_HYNIX_ID

        mock_stocks = [
            (1, "SK하이닉스", SK_HYNIX_ID),
            (2, "삼성전자", "KR7005930003"),
            (3, "카카오", "KR7035720002"),
        ]

        sk_only = _filter_targets(mock_stocks, "sk")
        self.assertEqual(len(sk_only), 1)
        self.assertEqual(sk_only[0][1], "SK하이닉스")

        others = _filter_targets(mock_stocks, "others")
        self.assertEqual(len(others), 2)
        self.assertNotIn("SK하이닉스", [s[1] for s in others])

        all_stocks = _filter_targets(mock_stocks, "all")
        self.assertEqual(len(all_stocks), 3)

        none_stocks = _filter_targets(mock_stocks, None)
        self.assertEqual(len(none_stocks), 3)


if __name__ == "__main__":
    unittest.main()
