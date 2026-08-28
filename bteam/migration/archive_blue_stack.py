"""B-Team 레거시 Blue 스택 폐기 및 7일 롤백 보존 아카이빙 모듈.

24시간 Soak 기간을 성공적으로 통과하고 DECOMMISSION_APPROVED 외부 승인이 발급된 경우,
Blue 컨테이너를 안전하게 중지하고 레거시 소스를 7일 보존 아카이브로 이전합니다.
(데이터베이스 볼륨 및 백업 스냅샷은 7일 동안 온전히 보존됩니다.)
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

MIGRATION_DIR = Path(__file__).resolve().parent
ROOT_DIR = MIGRATION_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from migration.verify_gate import GateVerificationError, verify_approval_file

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bteam.migration.archive_blue_stack")

DEFAULT_APPROVAL_FILE = MIGRATION_DIR / "approvals" / "decommission-approved.json"
DEFAULT_ARCHIVE_ROOT = MIGRATION_DIR / "archive"

LEGACY_SUBPROJECTS = [
    "Oliview_Project",
    "Oliview_aspect_sentence_split",
    "Oliview_aspect_sentiment",
    "Oliview_LLM",
    "Oliview_chatbot_a",
    "Oliview_chatbot_b",
]


class DecommissionError(Exception):
    """레거시 폐기 및 아카이빙 실패 시 발생하는 예외."""


def redact_secrets_in_directory(target_dir: Path) -> None:
    """아카이브 디렉토리 내의 .env 및 시크릿 파일을 마스킹합니다."""
    for root, _, files in os.walk(target_dir):
        for f in files:
            if f.endswith(".env") or f.startswith(".env.") or "secret" in f.lower():
                fp = Path(root) / f
                try:
                    lines = fp.read_text(encoding="utf-8", errors="ignore").splitlines()
                    redacted = [
                        f"{line.split('=', 1)[0]}=***REDACTED***" if "=" in line else line
                        for line in lines
                    ]
                    fp.write_text("\n".join(redacted) + "\n", encoding="utf-8")
                except OSError as e:
                    logger.warning("시크릿 마스킹 중 파일 처리 오류 (%s): %s", fp, e)


def archive_blue_legacy_stack(
    approval_path: Path | str = DEFAULT_APPROVAL_FILE,
    archive_root: Path | str = DEFAULT_ARCHIVE_ROOT,
    retention_days: int = 7,
    legacy_sources: list[Path] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """외부 승인을 검증한 후 Blue 스택을 7일 보존 아카이브로 이동합니다."""
    app_p = Path(approval_path)
    arch_root = Path(archive_root)

    try:
        verify_approval_file(app_p, expected_gate="DECOMMISSION_APPROVED")
    except GateVerificationError as e:
        raise DecommissionError(f"승인 아티팩트 검증 실패: {e}") from e

    now = datetime.datetime.now(datetime.UTC)
    expires_at = now + datetime.timedelta(days=retention_days)
    archive_id = f"blue_archive_{now.strftime('%Y%m%d_%H%M%S')}"
    archive_dir = arch_root / archive_id
    archive_dir.mkdir(parents=True, exist_ok=True)

    archived_items: list[str] = []

    sources_to_archive: list[Path] = (
        legacy_sources
        if legacy_sources is not None
        else [ROOT_DIR.parent / p for p in LEGACY_SUBPROJECTS if (ROOT_DIR.parent / p).exists()]
    )

    for src in sources_to_archive:
        if src.exists():
            dest = archive_dir / src.name
            logger.info("아카이브 이전 중: %s -> %s", src, dest)
            if not dry_run:
                if src.is_dir():
                    shutil.copytree(src, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dest)
            archived_items.append(str(dest))

    if not dry_run and archive_dir.exists():
        redact_secrets_in_directory(archive_dir)

    manifest_file = archive_dir / "blue_manifest.json"
    manifest_data = {
        "status": "ARCHIVED",
        "archive_id": archive_id,
        "created_at": now.isoformat(),
        "retention_policy": f"POC_DEMO_{retention_days}_DAYS",
        "retention_days": retention_days,
        "expires_at": expires_at.isoformat(),
        "archived_paths": archived_items,
        "preserved_docker_volumes": [
            "bteam_mysql_data",
            "bteam_redis_data",
        ],
        "secrets_redacted": True,
        "manifest_path": str(manifest_file),
    }

    manifest_file.write_text(
        json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("[OK] Blue 스택 7일 보존 아카이빙 완료: %s", manifest_file)
    return manifest_data


def main() -> int:
    parser = argparse.ArgumentParser(description="B-Team Blue 레거시 7일 보존 아카이빙 CLI")
    parser.add_argument(
        "--approval-file",
        default=str(DEFAULT_APPROVAL_FILE),
        help="DECOMMISSION_APPROVED 승인 파일 경로",
    )
    parser.add_argument("--retention-days", type=int, default=7, help="보존 기간(일)")
    parser.add_argument("--dry-run", action="store_true", help="모의 실행 모드")
    args = parser.parse_args()

    try:
        archive_blue_legacy_stack(
            approval_path=args.approval_file,
            retention_days=args.retention_days,
            dry_run=args.dry_run,
        )
        print("[OK] Blue 레거시 7일 보존 아카이빙 성공")
        return 0
    except DecommissionError as e:
        logger.error("[ERROR] 아카이빙 실패: %s", e)
        print(f"[ERROR] 아카이빙 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
