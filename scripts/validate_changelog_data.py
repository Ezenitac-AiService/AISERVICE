#!/usr/bin/env python3
"""Validates gateway/html/changelog_data.json against changelog_schema.json."""

from pathlib import Path
import json
import jsonschema

BASE_DIR = Path(__file__).resolve().parents[1]
SCHEMA_PATH = BASE_DIR / "specs" / "048-anti-fictional-user-and-citation-fidelity" / "contracts" / "changelog_schema.json"
DATA_PATH = BASE_DIR / "gateway" / "html" / "changelog_data.json"


def validate_changelog():
    assert SCHEMA_PATH.exists(), f"Schema file not found at {SCHEMA_PATH}"
    assert DATA_PATH.exists(), f"Data file not found at {DATA_PATH}"

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))

    jsonschema.validate(instance=data, schema=schema)
    print(f"[SUCCESS] Validated {len(data)} changelog entries against {SCHEMA_PATH.name}")


if __name__ == "__main__":
    validate_changelog()
