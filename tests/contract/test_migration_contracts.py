"""Contract tests for migration manifests, asset manifests, and healthcheck reports.

Enforces:
- FR-006: Database restore manifest integrity.
- FR-007: Exact 9 check IDs in verification suite.
- Migration asset manifest: path_base=AISERVICE_ROOT, 6 authoritative assets.
- JSON Schema conformance across contract definitions.
"""

from pathlib import Path
import json
import jsonschema
import pytest

@pytest.fixture
def schemas(contracts_dir: Path):
    with open(contracts_dir / "migration-manifest-schema.json", "r", encoding="utf-8") as f:
        migration_schema = json.load(f)
    with open(contracts_dir / "asset-manifest-schema.json", "r", encoding="utf-8") as f:
        asset_schema = json.load(f)
    with open(contracts_dir / "healthcheck-report-schema.json", "r", encoding="utf-8") as f:
        healthcheck_schema = json.load(f)
    return {
        "migration": migration_schema,
        "asset": asset_schema,
        "healthcheck": healthcheck_schema,
    }

def test_asset_manifest_schema_specifies_six_authoritative_assets(schemas):
    """asset-manifest-schema.json must enforce exactly 6 authoritative assets with path_base=AISERVICE_ROOT."""
    asset_schema = schemas["asset"]
    props = asset_schema.get("properties", {})
    assert props.get("path_base", {}).get("const") == "AISERVICE_ROOT"

    items = props.get("assets", {}).get("items", {})
    item_props = items.get("properties", {})
    asset_ids = item_props.get("asset_id", {}).get("enum", [])
    expected_assets = {"qwen3.5-4b", "qwen3.5-2b", "bge-m3", "bge-reranker-v2-m3", "pilos-rag-chroma", "chata-chroma-bm25"}
    assert set(asset_ids) == expected_assets
    assert props.get("assets", {}).get("minItems") == 6
    assert props.get("assets", {}).get("maxItems") == 6

def test_healthcheck_schema_specifies_exact_nine_check_ids(schemas):
    """healthcheck-report-schema.json must specify exactly 9 top-level check IDs."""
    hc_schema = schemas["healthcheck"]
    # Check checks array items id enum
    checks_def = hc_schema.get("properties", {}).get("checks", {}).get("items", {})
    check_id_enum = checks_def.get("properties", {}).get("id", {}).get("enum", [])
    expected_nine = {
        "portal", "ateam_pilos", "bteam_oliview", "bteam_chata", "bteam_chatb",
        "model_gateway_llm", "model_gateway_embedding", "model_gateway_rerank", "redis"
    }
    assert set(check_id_enum) == expected_nine
    assert len(check_id_enum) == 9

def test_existing_migration_manifest_conforms_to_schema(aiservice_root: Path, schemas):
    """The migration manifest in AISERVICE/migration_pack must conform to migration-manifest-schema.json."""
    manifest_path = aiservice_root / "migration_pack" / "migration_manifest.json"
    assert manifest_path.exists(), f"migration_manifest.json not found at {manifest_path}"
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    jsonschema.validate(instance=data, schema=schemas["migration"])

def test_existing_asset_manifest_conforms_to_schema(aiservice_root: Path, schemas):
    """The asset manifest in AISERVICE/migration_pack must conform to asset-manifest-schema.json."""
    asset_path = aiservice_root / "migration_pack" / "asset_manifest.json"
    assert asset_path.exists(), f"asset_manifest.json not found at {asset_path}"
    with open(asset_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    jsonschema.validate(instance=data, schema=schemas["asset"])

def test_existing_verification_report_conforms_to_schema(aiservice_root: Path, schemas):
    """The verification report in AISERVICE/migration_pack must conform to healthcheck-report-schema.json."""
    report_path = aiservice_root / "migration_pack" / "verification_report.json"
    assert report_path.exists(), f"verification_report.json not found at {report_path}"
    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    jsonschema.validate(instance=data, schema=schemas["healthcheck"])
