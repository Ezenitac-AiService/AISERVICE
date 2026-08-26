"""
Unit/Integration Test Suite for SQLite DB Seed & Setup Integration (045-db-seed-and-setup-integration).
Strict Anti-Mock Real Execution per Constitution v1.4.0.
"""

import os
import pytest
from scripts.seed_db import seed_database
from src.core.metrics_db import MetricsDB, DB_PATH
from src.core.config_manager import ConfigManager


def test_seed_database_execution():
    # 1. Run seed_database script
    seed_database(reset=True)
    assert os.path.exists(DB_PATH), f"Expected DB file at {DB_PATH}"

    # 2. Check seed API keys registered in server_config.json
    cm = ConfigManager()
    cfg = cm.get_server_config()
    keys = cfg.get("api_keys", [])
    key_strings = [(k.get("key") if isinstance(k, dict) else k) for k in keys]
    assert "sk-vllm-dev-demo1" in key_strings
    assert "sk-vllm-mobile-app" in key_strings

    # 3. Check seeded metrics in DB
    db = MetricsDB(db_path=DB_PATH)
    metrics = db.get_aggregated_metrics()
    assert len(metrics) > 0, "Expected non-empty seeded metrics"

    # Verify seed record fields
    payload = db.get_payload_by_id(1)
    assert payload is not None
    assert "prompt_text" in payload
    assert "completion_text" in payload

    # 4. Check new endpoints (/v1/embeddings and /v1/rerank) seeded in DB (054-seedpack-setup-sync)
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT endpoint FROM api_key_logs")
    endpoints = [row[0] for row in cursor.fetchall()]
    conn.close()

    assert "/v1/embeddings" in endpoints, "Expected /v1/embeddings in seeded database metrics"
    assert "/v1/rerank" in endpoints, "Expected /v1/rerank in seeded database metrics"
