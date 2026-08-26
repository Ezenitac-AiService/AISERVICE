"""기존 익명화 실행기: 이미 모아 둔 원본 JSONL(data/raw/*)의 식별자를 비식별화한다.

크롤링 없이, 백필/증분이 남긴 `until_*` · `from_*` JSONL 파일을 읽어 각 레코드의
author.userProfileId · author.nickname · authorUserProfileId 를 data_masking 으로
해싱한 뒤 파일을 제자리(in-place)로 다시 쓴다. 마스킹이 크롤러에 붙기 이전에 모은
과거분을 뒤늦게 익명화하는 용도.

- 멱등: 이미 해시된 값(64자리 hex)은 다시 해싱하지 않는다(증분이 이미 마스킹한 파일 대비).
- 보존: 식별자가 없거나 손상된 레코드도 버리지 않고 원문 그대로 유지한다(크롤러와 달리 필터 아님).
- 안전: 임시파일 + os.replace 로 원자적 교체. 해싱은 단방향이라 되돌릴 수 없으므로
        먼저 DRY_RUN=True 로 건수만 확인한 뒤 실제 실행을 권장한다.

실행: uv run python -m pilos.jobs.maintenance.anonymize_legacy_comments
"""
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

from pilos.collection.data_masking import (
    MaskingSaltUnavailableError,
    anonymize_nickname,
    anonymize_user_profile_id,
    require_salts,
)
from pilos.collection.logging_setup import setup_logging
from pilos.storage.json_io import get_data_dir

logger = logging.getLogger(__name__)

# ==========================================================================
# 설정 (여기 값만 바꿔서 실행)
# ==========================================================================
# 익명화 대상 파일 glob(원본 댓글 JSONL). 백필(until_*) + 증분(from_*) 전부.
FILE_GLOBS = ("until_*_comment.jsonl", "from_*_comment.jsonl")
# True 면 파일을 쓰지 않고 익명화될 건수만 집계해 로그로 미리 보여준다(안전 점검용).
# 제자리 덮어쓰기는 되돌릴 수 없으므로 기본은 미리보기. 확인 후 False 로 바꿔 실제 실행한다.
DRY_RUN = True
# ==========================================================================


def _looks_hashed(value) -> bool:
    """값이 이미 SHA-256 해시(64자리 소문자 hex 문자열)처럼 보이면 True(이중 해싱 방지)."""
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


def _mask_record(record: dict) -> bool:
    """레코드의 식별자 필드를 제자리 해싱한다. 하나라도 바꿨으면 True.

    이미 해시된 값·결측 필드는 건드리지 않는다(멱등·보존).
    """
    changed = False
    author = record.get("author")
    if isinstance(author, dict):
        profile_id = author.get("userProfileId")
        if profile_id is not None and not _looks_hashed(profile_id):
            author["userProfileId"] = anonymize_user_profile_id(profile_id)
            changed = True
        nickname = author.get("nickname")
        if nickname is not None and not _looks_hashed(nickname):
            author["nickname"] = anonymize_nickname(nickname)
            changed = True

    profile_id_2 = record.get("authorUserProfileId")
    if profile_id_2 is not None and not _looks_hashed(profile_id_2):
        record["authorUserProfileId"] = anonymize_user_profile_id(profile_id_2)
        changed = True

    return changed


def _process_dry(path: Path) -> tuple[int, int]:
    """파일을 읽기만 하며 (총 레코드, 익명화 대상 레코드) 수를 센다(쓰기 없음)."""
    total = 0
    masked = 0
    with open(path, mode="r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue   # 손상 줄은 그대로 두므로 집계에서 제외
            if _mask_record(record):   # dry 에선 복제본을 바꿔 판정만(원본 미변경)
                masked += 1
    return total, masked


def _process_write(path: Path) -> tuple[int, int]:
    """파일을 익명화해 원자적으로 제자리 교체하고 (총 레코드, 익명화 레코드) 수를 반환한다."""
    total = 0
    masked = 0
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")   # 반드시 같은 디렉터리
    try:
        with os.fdopen(fd, mode="w", encoding="utf-8") as out, \
             open(path, mode="r", encoding="utf-8-sig") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                total += 1
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError:
                    # 손상 줄은 파싱하지 않고 원문 그대로 보존한다(데이터 손실 방지).
                    out.write(stripped + "\n")
                    continue
                if _mask_record(record):
                    masked += 1
                out.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            out.flush()
            os.fsync(out.fileno())   # 디스크까지 확정(전원 차단 대비)
        os.replace(tmp, path)        # Windows/POSIX 모두 원자적 교체
    except BaseException:
        Path(tmp).unlink(missing_ok=True)   # 실패 시 임시파일 정리(원본 보존)
        raise
    return total, masked


def _iter_target_files():
    """data/raw 아래 대상 JSONL 파일 경로를 정렬해 순회한다(중복 경로 제거)."""
    data_dir = get_data_dir()
    seen = set()
    for pattern in FILE_GLOBS:
        for path in sorted(data_dir.glob(pattern)):
            if path not in seen:
                seen.add(path)
                yield path


def main():
    """대상 JSONL 을 모두 익명화한다(파일별 오류는 격리).

    익명화 실패 파일이 하나라도 있으면 종료코드 1 을 반환한다.
    """
    setup_logging()
    # 솔트가 없으면 _mask_record 가 anonymize_* 에서 TypeError 로 죽는다(DRY_RUN 도 마스킹을
    # 계산하므로 동일). 파일을 열기 전에 시작 단계에서 명확히 중단한다(3.4).
    try:
        require_salts()
    except MaskingSaltUnavailableError as e:
        logger.error(f"[익명화 종료] 비식별화 솔트 미설정으로 시작하지 못함: {e}")
        return 1
    files = list(_iter_target_files())
    if not files:
        logger.warning(f"익명화할 파일이 없습니다(패턴 {FILE_GLOBS} @ {get_data_dir()})")
        return 0

    mode = "DRY-RUN(미리보기)" if DRY_RUN else "실제 익명화(제자리 덮어쓰기)"
    logger.info(f"[익명화 시작] {mode} · 대상 {len(files)}개 파일")
    total_records = 0
    total_masked = 0
    failures = []
    for path in files:
        try:
            if DRY_RUN:
                total, masked = _process_dry(path)
            else:
                total, masked = _process_write(path)
            total_records += total
            total_masked += masked
            logger.info(f"  {path.name}: {masked}/{total}건 익명화")
        except Exception:
            logger.exception(f"  {path.name}: 익명화 실패 - 다음 파일로 진행")
            failures.append(path.name)

    ok = len(files) - len(failures)
    tail = " (DRY-RUN, 파일은 변경되지 않음)" if DRY_RUN else ""
    if failures:
        logger.error(f"[익명화 종료] 성공 {ok}/{len(files)}개 파일 · "
                     f"{total_masked}/{total_records}건 익명화 · 실패 {failures}{tail}")
        return 1
    logger.info(f"[익명화 종료] 성공 {ok}/{len(files)}개 파일 · "
                f"{total_masked}/{total_records}건 익명화{tail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
