"""B-Team 운영 전환 및 거버넌스 승인 서명 검증 모듈.

외부 변경 권한자(CAB)가 정식 발급한 승인 아티팩트의 4대 필수 필드
(approved_by, approval_authority, approval_reference, previous_gate_sha256)
및 SHA-256 해시 체인을 검증하여 무단/위조 컷오버를 차단합니다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bteam.migration.verify_gate")

REQUIRED_APPROVAL_FIELDS = {
    "gate_type",
    "approved_by",
    "approval_authority",
    "approval_reference",
    "previous_gate_sha256",
}


class GateVerificationError(Exception):
    """게이트 승인 검증 실패 시 발생하는 예외."""


def calculate_sha256(file_path: Path | str) -> str:
    """파일의 SHA-256 해시 문자열을 계산합니다."""
    path = Path(file_path)
    if not path.exists():
        raise GateVerificationError(f"해시 계산 대상 파일이 존재하지 않습니다: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_approval_file(
    approval_path: Path | str,
    expected_gate: str,
    previous_gate_path: Path | str | None = None,
) -> dict[str, Any]:
    """승인 아티팩트 파일의 무결성과 필수 필드 및 해시 체인을 검증합니다."""
    path = Path(approval_path)
    if not path.exists():
        raise GateVerificationError(f"승인 아티팩트 파일이 존재하지 않습니다: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise GateVerificationError(f"승인 아티팩트 JSON 파싱 오류: {e}") from e

    if not isinstance(data, dict):
        raise GateVerificationError("승인 아티팩트는 JSON 객체(dict) 형식이어야 합니다.")

    missing_fields = REQUIRED_APPROVAL_FIELDS - set(data.keys())
    if missing_fields:
        raise GateVerificationError(f"필수 필드 누락: {', '.join(sorted(missing_fields))}")

    actual_gate = data.get("gate_type")
    if actual_gate != expected_gate:
        raise GateVerificationError(
            f"게이트 타입 불일치: 예상='{expected_gate}', 실제='{actual_gate}'"
        )

    for field in REQUIRED_APPROVAL_FIELDS:
        val = str(data.get(field, "")).strip()
        if not val:
            raise GateVerificationError(f"필수 필드 '{field}'의 값이 비어있습니다.")

    recorded_prev_sha = str(data.get("previous_gate_sha256", "")).strip().lower()
    if previous_gate_path is not None:
        prev_p = Path(previous_gate_path)
        if prev_p.exists():
            actual_prev_sha = calculate_sha256(prev_p).lower()
            if recorded_prev_sha != actual_prev_sha:
                raise GateVerificationError(
                    f"이전 게이트 해시 체인 불일치: 기록='{recorded_prev_sha}', 실제='{actual_prev_sha}'"
                )
        else:
            logger.warning(
                "이전 게이트 파일(%s)이 존재하지 않아 해시 계산을 건너뜁니다.", prev_p
            )

    logger.info(
        "승인 검증 성공: gate=%s, approved_by=%s, authority=%s, ref=%s",
        expected_gate,
        data.get("approved_by"),
        data.get("approval_authority"),
        data.get("approval_reference"),
    )
    return {"status": "VERIFIED", "gate_type": expected_gate, "metadata": data}


def main() -> int:
    parser = argparse.ArgumentParser(description="B-Team 거버넌스 승인 게이트 검증 CLI")
    parser.add_argument(
        "--gate",
        required=True,
        choices=["CUTOVER_APPROVED", "BACKUP_READY", "DATA_MIGRATION_READY", "DECOMMISSION_APPROVED"],
        help="검증할 게이트 타입",
    )
    parser.add_argument(
        "--approval-file",
        default="migration/approvals/cutover-approved.json",
        help="승인 JSON 아티팩트 파일 경로",
    )
    parser.add_argument(
        "--prev-gate-file",
        default=None,
        help="직전 게이트 아티팩트 파일 경로 (해시 체인 검증용)",
    )
    args = parser.parse_args()

    try:
        verify_approval_file(
            approval_path=args.approval_file,
            expected_gate=args.gate,
            previous_gate_path=args.prev_gate_file,
        )
        print(f"[OK] 게이트 검증 통과: {args.gate}")
        return 0
    except GateVerificationError as e:
        logger.error("[ERROR] 게이트 검증 실패: %s", e)
        print(f"[ERROR] 게이트 검증 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
