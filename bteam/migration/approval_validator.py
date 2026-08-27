from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

APPROVAL_TYPES = {
    "CUTOVER_APPROVED",
    "BACKUP_READY",
    "DATA_MIGRATION_READY",
    "DECOMMISSION_APPROVED",
}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_gate_artifact(
    artifact: dict[str, Any], *, expected_type: str | None = None
) -> None:
    gate_type = artifact.get("gate_type")
    if gate_type not in APPROVAL_TYPES:
        raise ValueError("unsupported gate type")
    if expected_type and gate_type != expected_type:
        raise ValueError("gate type does not match expected transition")
    if artifact.get("decision") != "APPROVED":
        raise ValueError("gate is not approved")
    for field in ("environment", "recorded_by", "recorded_at"):
        if not artifact.get(field):
            raise ValueError(f"missing gate field: {field}")
    if gate_type in {"CUTOVER_APPROVED", "DECOMMISSION_APPROVED"}:
        for field in ("approved_by", "approval_authority", "approval_reference"):
            if not artifact.get(field):
                raise ValueError(f"missing external approval field: {field}")
    if gate_type == "DATA_MIGRATION_READY":
        if any(
            artifact.get(key) != 0
            for key in ("delta_lag", "chroma_v1_lag", "chroma_v2_lag")
        ):
            raise ValueError("data migration lag must be zero")
        if artifact.get("rollback_compatible") is not True:
            raise ValueError("rollback compatibility is required")


def load_gate(path: str | Path, *, expected_type: str | None = None) -> dict[str, Any]:
    artifact = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_gate_artifact(artifact, expected_type=expected_type)
    return artifact
