import json
from pathlib import Path

from migration.execute_drain_backup import execute_drain_and_backup

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = ROOT / "migration" / "artifacts"


def test_execute_drain_and_backup(tmp_path):
    out_snapshot = tmp_path / "test_snapshot.sql"
    out_artifact = tmp_path / "backup-ready.json"

    result = execute_drain_and_backup(
        drain_timeout_seconds=5.0,
        snapshot_path=out_snapshot,
        artifact_path=out_artifact,
        mock_db=True,
    )

    assert result["gate_type"] == "BACKUP_READY"
    assert result["status"] == "COMPLETED"
    assert out_snapshot.exists()
    assert out_artifact.exists()

    artifact_data = json.loads(out_artifact.read_text(encoding="utf-8"))
    assert artifact_data["gate_type"] == "BACKUP_READY"
    assert "mysql_dump_sha256" in artifact_data
    assert artifact_data["in_flight_drain_seconds"] <= 5.0
