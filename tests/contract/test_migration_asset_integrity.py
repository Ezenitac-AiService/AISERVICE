"""Contract tests for migration asset integrity and manifest validation (T054).

Enforces:
- 6 required assets in asset_manifest.json
- Validation against asset-manifest-schema.json
- Exclusion of legacy and green files
"""

from pathlib import Path
import json
import pytest
import jsonschema

def test_asset_manifest_conforms_to_schema(aiservice_root: Path, contracts_dir: Path):
    manifest_path = aiservice_root / "migration_pack" / "asset_manifest.json"
    schema_path = contracts_dir / "asset-manifest-schema.json"

    assert manifest_path.exists(), f"Missing {manifest_path}"
    assert schema_path.exists(), f"Missing {schema_path}"

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    jsonschema.validate(instance=data, schema=schema)

def test_asset_manifest_contains_six_authoritative_assets(aiservice_root: Path):
    manifest_path = aiservice_root / "migration_pack" / "asset_manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    expected_assets = {
        "qwen3.5-4b",
        "qwen3.5-2b",
        "bge-m3",
        "bge-reranker-v2-m3",
        "pilos-rag-chroma",
        "chata-chroma-bm25",
    }
    actual_assets = {a["asset_id"] for a in data.get("assets", [])}
    assert actual_assets == expected_assets
    assert len(data.get("assets", [])) == 6
