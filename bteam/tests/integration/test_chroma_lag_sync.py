import json
from pathlib import Path

from migration.sync_final_delta import sync_final_delta_and_verify

ROOT = Path(__file__).resolve().parents[2]


def test_sync_final_delta_lag_zero_success(tmp_path):
    artifact_file = tmp_path / "data-migration-ready.json"

    result = sync_final_delta_and_verify(
        mysql_analyzed_count=1000,
        chroma_v2_count=1000,
        artifact_path=artifact_file,
    )

    assert result["gate_type"] == "DATA_MIGRATION_READY"
    assert result["status"] == "COMPLETED"
    assert result["chroma_lag_records"] == 0
    assert artifact_file.exists()

    data = json.loads(artifact_file.read_text(encoding="utf-8"))
    assert data["gate_type"] == "DATA_MIGRATION_READY"
    assert data["chroma_lag_records"] == 0


def test_sync_final_delta_lag_positive_syncs_to_zero(tmp_path):
    artifact_file = tmp_path / "data-migration-ready.json"

    # 1000 vs 950 -> sync_final_delta_and_verify will sync missing 50 delta items
    result = sync_final_delta_and_verify(
        mysql_analyzed_count=1000,
        chroma_v2_count=950,
        artifact_path=artifact_file,
    )

    assert result["gate_type"] == "DATA_MIGRATION_READY"
    assert result["chroma_lag_records"] == 0
    assert result["synced_delta_records"] == 50
