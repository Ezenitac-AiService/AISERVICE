import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# 모든 실행기는 저장소 루트의 단일 .env를 사용한다.
load_dotenv(PROJECT_ROOT / ".env")
#=================================================================
SECRET_SALT = os.getenv("SECRET_SALT")
SECRET_SALT2 = os.getenv("SECRET_SALT2")
CREATED_AT_FORMAT = "%Y-%m-%d %H:%M:%S"
#=================================================================


class MaskingSaltUnavailableError(RuntimeError):
    """비식별화 솔트가 없어 마스킹을 시작할 수 없음(실행 시작 단계 fail-fast).

    솔트 미설정 상태로 anonymize_* 를 호출하면 `str(x) + None` 이 되어 댓글 루프
    중간에 TypeError 로 죽는다. 실행기는 시작 단계에서 require_salts() 로 이 예외를
    먼저 발생시켜, 크롤링 도중이 아니라 시작 전에 명확히 중단하도록 한다.
    """


def require_salts():
    """마스킹에 필요한 솔트가 모두 설정됐는지 실행 시작 단계에서 확인한다.

    SECRET_SALT/SECRET_SALT2 중 하나라도 비어 있으면(None·빈 문자열·공백)
    MaskingSaltUnavailableError 로 즉시 중단한다. 여기서 검사하는 값은 anonymize_*
    가 실제로 사용하는 모듈 전역과 동일하며, 솔트는 저장소 루트 .env에서
    모듈 로드 시 읽는다.
    """
    missing = [
        name
        for name, value in (("SECRET_SALT", SECRET_SALT), ("SECRET_SALT2", SECRET_SALT2))
        if not (value and value.strip())
    ]
    if missing:
        raise MaskingSaltUnavailableError(
            f"비식별화 솔트 미설정: {', '.join(missing)}. "
            "저장소 루트 .env에 값을 설정하세요 "
            "(copy .env.example .env)."
        )


def anonymize_nickname(nickname: str | None) -> str:
    """닉네임을 안전하게 비식별화(해싱)하는 함수 (None/공백 시 '익명' fallback)"""
    if not nickname or not str(nickname).strip():
        nickname = "익명"
    salted_name = str(nickname).strip() + (SECRET_SALT or "")
    hash_obj = hashlib.sha256(salted_name.encode('utf-8'))
    return hash_obj.hexdigest()

def anonymize_user_profile_id(user_profile_id: str | None) -> str:
    """프로필 아이디를 안전하게 비식별화(해싱)하는 함수 (None/공백 시 'ANONYMOUS_USER' fallback)"""
    if not user_profile_id or not str(user_profile_id).strip():
        user_profile_id = "ANONYMOUS_USER"
    salted_name = str(user_profile_id).strip() + (SECRET_SALT2 or "")
    hash_obj = hashlib.sha256(salted_name.encode('utf-8'))
    return hash_obj.hexdigest()

