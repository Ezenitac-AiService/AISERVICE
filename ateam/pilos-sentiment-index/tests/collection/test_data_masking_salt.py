"""비식별화 솔트 fail-fast(3.4) 계약 테스트.

솔트(SECRET_SALT/SECRET_SALT2)가 없으면 댓글 루프 중간에 TypeError 로 죽는 대신,
실행 시작 단계에서 명확히 중단해야 한다. 네트워크·DB 없이 계약만 검증한다.

핵심 검증:
- require_salts(): 값이 모두 있으면 통과, 하나라도 비면 MaskingSaltUnavailableError.
- 세 실행기 main(): 솔트 누락 시 DB/네트워크에 닿기 전에 종료코드 1 을 반환.

실행:  uv run python -m unittest discover -s tests/collection -p "test_data_masking_salt.py"
"""
import unittest
from unittest import mock

from pilos.collection import data_masking as dm


def _patch_salts(salt="s1", salt2="s2"):
    """data_masking 모듈 전역 솔트를 임시 교체한다(anonymize_* 가 쓰는 실제 값)."""
    return mock.patch.multiple(dm, SECRET_SALT=salt, SECRET_SALT2=salt2)


class RequireSaltsTest(unittest.TestCase):
    def test_passes_when_both_present(self):
        with _patch_salts("ezen", "studio"):
            dm.require_salts()   # 예외가 없어야 한다

    def test_raises_when_missing_or_blank(self):
        # None·빈 문자열·공백만 있는 값은 모두 '미설정'으로 본다.
        cases = [
            (None, "s2"),
            ("s1", None),
            ("", "s2"),
            ("s1", "   "),
            (None, None),
        ]
        for salt, salt2 in cases:
            with self.subTest(salt=salt, salt2=salt2):
                with _patch_salts(salt, salt2):
                    with self.assertRaises(dm.MaskingSaltUnavailableError):
                        dm.require_salts()

    def test_error_message_names_missing_keys(self):
        with _patch_salts(None, None):
            with self.assertRaises(dm.MaskingSaltUnavailableError) as ctx:
                dm.require_salts()
        msg = str(ctx.exception)
        self.assertIn("SECRET_SALT", msg)
        self.assertIn("SECRET_SALT2", msg)


class RunnerFailFastTest(unittest.TestCase):
    """솔트 누락 시 각 실행기 main() 이 DB/네트워크 이전에 종료코드 1 을 반환한다.

    require_salts() 가 require_connection() 보다 먼저 실행되므로, 솔트를 비우면
    DB 접속·크롤링에 닿지 않고 중단된다(그래서 DB 스텁 없이도 검증 가능).
    """

    def test_incremental_main_exits_1(self):
        from pilos.jobs import incremental_comments as inc
        with _patch_salts(None, None), mock.patch.object(inc, "setup_logging"):
            self.assertEqual(inc.main(target="sk"), 1)

    def test_backfill_main_exits_1(self):
        from pilos.jobs import backfill_comments as bf
        with _patch_salts(None, None), mock.patch.object(bf, "setup_logging"):
            self.assertEqual(bf.main(target="sk"), 1)

    def test_anonymize_main_exits_1(self):
        from pilos.jobs.maintenance import anonymize_legacy_comments as anon
        with _patch_salts(None, None), mock.patch.object(anon, "setup_logging"):
            self.assertEqual(anon.main(), 1)


if __name__ == "__main__":
    unittest.main()
