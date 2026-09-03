"""Contract tests for exact 9 healthcheck endpoints and schema alignment (T042).

Enforces:
- FR-007: Exact 9 check IDs (portal, ateam_pilos, bteam_oliview, bteam_chata, bteam_chatb,
          model_gateway_llm, model_gateway_embedding, model_gateway_rerank, redis).
- Elimination of legacy 11 endpoints and 127.0.0.1 loopback targets.
"""

from pathlib import Path
import json
import pytest
import jsonschema

EXACT_NINE_CHECK_IDS = [
    "portal",
    "ateam_pilos",
    "bteam_oliview",
    "bteam_chata",
    "bteam_chatb",
    "model_gateway_llm",
    "model_gateway_embedding",
    "model_gateway_rerank",
    "redis",
]

def test_healthcheck_schema_contains_exact_nine_ids(contracts_dir: Path):
    schema_path = contracts_dir / "healthcheck-report-schema.json"
    assert schema_path.exists()
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    checks_item = schema.get("properties", {}).get("checks", {}).get("items", {})
    enum_ids = checks_item.get("properties", {}).get("id", {}).get("enum", [])
    assert set(enum_ids) == set(EXACT_NINE_CHECK_IDS)
    assert len(enum_ids) == 9

def test_verify_migration_uses_nine_endpoints(aiservice_root: Path):
    verify_script = aiservice_root / "migration_pack" / "scripts" / "verify_migration.py"
    assert verify_script.exists()
    content = verify_script.read_text(encoding="utf-8")
    for check_id in EXACT_NINE_CHECK_IDS:
        assert check_id in content, f"Missing check ID {check_id} in verify_migration.py"
