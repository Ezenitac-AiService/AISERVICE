import json
from pathlib import Path

import pytest

from migration.archive_blue_stack import DecommissionError, archive_blue_legacy_stack

ROOT = Path(__file__).resolve().parents[2]


def test_archive_blue_missing_approval_fails(tmp_path):
    with pytest.raises(DecommissionError, match="승인 아티팩트"):
        archive_blue_legacy_stack(
            approval_path=tmp_path / "non_existent_approval.json",
            archive_root=tmp_path / "archive",
            dry_run=True,
        )


def test_archive_blue_with_valid_approval_creates_7day_manifest(tmp_path):
    approval_file = tmp_path / "decommission-approved.json"
    approval_data = {
        "gate_type": "DECOMMISSION_APPROVED",
        "approved_by": "lead-cab@ezenitac.com",
        "approval_authority": "Production CAB",
        "approval_reference": "CAB-20260828-DECOM-01",
        "approved_at": "2026-08-28T16:00:00Z",
        "previous_gate_sha256": "a" * 64,
    }
    approval_file.write_text(json.dumps(approval_data), encoding="utf-8")

    # Create dummy legacy folder
    dummy_legacy = tmp_path / "legacy_src"
    dummy_legacy.mkdir()
    (dummy_legacy / "secret.env").write_text("DB_PASSWORD=supersecret\n", encoding="utf-8")

    archive_root = tmp_path / "archive"

    result = archive_blue_legacy_stack(
        approval_path=approval_file,
        archive_root=archive_root,
        retention_days=7,
        legacy_sources=[dummy_legacy],
        dry_run=True,
    )

    assert result["status"] == "ARCHIVED"
    assert result["retention_policy"] == "POC_DEMO_7_DAYS"
    assert "expires_at" in result
    assert result["preserved_docker_volumes"] == ["bteam_mysql_data", "bteam_redis_data"]

    manifest_file = Path(result["manifest_path"])
    assert manifest_file.exists()
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest_data["secrets_redacted"] is True
