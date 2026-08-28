import json
from pathlib import Path

import pytest

from migration.verify_gate import GateVerificationError, verify_approval_file

ROOT = Path(__file__).resolve().parents[2]
SPEC_042 = ROOT.parent / "specs" / "042-bteam-production-cutover"


def test_cutover_gate_schema_requires_4_fields():
    schema = json.loads(
        (SPEC_042 / "contracts" / "cutover_gate_contract.json").read_text(
            encoding="utf-8"
        )
    )
    required = schema["required"]
    assert {
        "gate_type",
        "approved_by",
        "approval_authority",
        "approval_reference",
        "previous_gate_sha256",
    }.issubset(required)


def test_verify_approval_valid(tmp_path):
    approval_file = tmp_path / "cutover-approved.json"
    dummy_prev = tmp_path / "preflight.json"
    dummy_prev.write_text('{"status": "READY"}', encoding="utf-8")
    import hashlib

    prev_sha = hashlib.sha256(dummy_prev.read_bytes()).hexdigest()

    data = {
        "gate_type": "CUTOVER_APPROVED",
        "approved_by": "lead-sre@ezenitac.com",
        "approval_authority": "Production CAB",
        "approval_reference": "CAB-20260828-01",
        "approved_at": "2026-08-28T14:00:00Z",
        "target_environment": "DEMO",
        "previous_gate_sha256": prev_sha,
    }
    approval_file.write_text(json.dumps(data), encoding="utf-8")

    result = verify_approval_file(
        approval_path=approval_file,
        expected_gate="CUTOVER_APPROVED",
        previous_gate_path=dummy_prev,
    )
    assert result["status"] == "VERIFIED"
    assert result["gate_type"] == "CUTOVER_APPROVED"


def test_verify_approval_missing_field_fails(tmp_path):
    approval_file = tmp_path / "cutover-approved.json"
    data = {
        "gate_type": "CUTOVER_APPROVED",
        "approved_by": "lead-sre@ezenitac.com",
        # missing approval_authority, approval_reference, previous_gate_sha256
    }
    approval_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(GateVerificationError, match="필수 필드 누락"):
        verify_approval_file(
            approval_path=approval_file,
            expected_gate="CUTOVER_APPROVED",
        )


def test_verify_approval_hash_mismatch_fails(tmp_path):
    approval_file = tmp_path / "cutover-approved.json"
    dummy_prev = tmp_path / "preflight.json"
    dummy_prev.write_text('{"status": "READY"}', encoding="utf-8")

    data = {
        "gate_type": "CUTOVER_APPROVED",
        "approved_by": "lead-sre@ezenitac.com",
        "approval_authority": "Production CAB",
        "approval_reference": "CAB-20260828-01",
        "approved_at": "2026-08-28T14:00:00Z",
        "target_environment": "DEMO",
        "previous_gate_sha256": "0" * 64,  # wrong hash
    }
    approval_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(GateVerificationError, match="해시 체인 불일치"):
        verify_approval_file(
            approval_path=approval_file,
            expected_gate="CUTOVER_APPROVED",
            previous_gate_path=dummy_prev,
        )
