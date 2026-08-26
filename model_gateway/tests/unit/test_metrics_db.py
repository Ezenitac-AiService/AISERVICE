"""
Unit tests for MetricsDB SQLite corruption quarantine and auto-healing recovery (066-metrics-db-auto-recovery).
"""

import os
import glob
import sqlite3
import pytest
from src.core.metrics_db import MetricsDB


def test_metrics_db_corrupt_file_quarantine_and_recovery(tmp_path):
    """US1 / FR-001 ~ FR-003: Verify malformed SQLite db file is quarantined and fresh DB created."""
    corrupt_db_path = tmp_path / "metrics.db"
    
    # Write invalid corrupted header bytes
    with open(corrupt_db_path, "wb") as f:
        f.write(b"INVALID_MALFORMED_SQLITE3_HEADER_DATA_1234567890\x00\xff")

    # Instantiate MetricsDB with corrupt file
    db = MetricsDB(db_path=str(corrupt_db_path))

    # Verify corrupt file was moved to a quarantine backup file
    quarantine_files = glob.glob(str(tmp_path / "metrics.db.corrupt_*"))
    assert len(quarantine_files) >= 1, "Corrupt DB file must be quarantined"

    # Verify fresh metrics.db exists and accepts inserts
    assert corrupt_db_path.exists(), "Fresh metrics.db must be recreated"
    db.log_request(api_key="test-key-01", endpoint="/v1/chat/completions", status_code=200, prompt_tokens=10, completion_tokens=20)

    metrics = db.get_aggregated_metrics()
    assert len(metrics) == 1
    assert metrics[0]["api_key"] == "test-key-01"
    assert metrics[0]["request_count"] == 1


def test_metrics_db_wal_file_cleanup_on_corrupt(tmp_path):
    """FR-002: Verify corrupt .db-wal and .db-shm files are quarantined along with .db."""
    corrupt_db_path = tmp_path / "metrics.db"
    wal_path = tmp_path / "metrics.db-wal"
    shm_path = tmp_path / "metrics.db-shm"

    corrupt_db_path.write_bytes(b"CORRUPT_HEADER")
    wal_path.write_bytes(b"CORRUPT_WAL")
    shm_path.write_bytes(b"CORRUPT_SHM")

    db = MetricsDB(db_path=str(corrupt_db_path))

    quarantine_db = glob.glob(str(tmp_path / "metrics.db.corrupt_*"))
    quarantine_wal = glob.glob(str(tmp_path / "metrics.db-wal.corrupt_*"))
    quarantine_shm = glob.glob(str(tmp_path / "metrics.db-shm.corrupt_*"))

    assert len(quarantine_db) >= 1
    assert len(quarantine_wal) >= 1
    assert len(quarantine_shm) >= 1

    # Normal DB queries should succeed
    sess = db.create_playground_session("sess-1", "Test Session")
    assert sess["id"] == "sess-1"


def test_metrics_db_in_memory_fallback_on_readonly_dir(tmp_path, monkeypatch):
    """FR-004: Verify fallback to :memory: DB when filesystem operations fail."""
    corrupt_db_path = tmp_path / "metrics.db"
    corrupt_db_path.write_bytes(b"CORRUPT_HEADER")

    # Mock shutil.move to raise OSError to simulate readonly filesystem
    def mock_move_fail(src, dst):
        raise OSError("Permission denied / Read-only file system")

    monkeypatch.setattr("shutil.move", mock_move_fail)

    db = MetricsDB(db_path=str(corrupt_db_path))

    # Verify fallback to :memory: or healthy connection
    db.log_request(api_key="readonly-test", endpoint="/v1/chat/completions", status_code=200)
    metrics = db.get_aggregated_metrics()
    assert len(metrics) == 1
    assert metrics[0]["api_key"] == "readonly-test"


def test_metrics_db_fresh_file_creation_when_deleted(tmp_path):
    """FR-003: Verify fresh MetricsDB is created and tables initialized when file is deleted."""
    non_existent_db_path = tmp_path / "new_metrics.db"
    assert not non_existent_db_path.exists()

    db = MetricsDB(db_path=str(non_existent_db_path))

    assert non_existent_db_path.exists()
    db.log_request(api_key="fresh-db-key", endpoint="/v1/chat/completions", status_code=200)
    metrics = db.get_aggregated_metrics()
    assert len(metrics) == 1
    assert metrics[0]["api_key"] == "fresh-db-key"

