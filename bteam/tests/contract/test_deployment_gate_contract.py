import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FEATURE = ROOT.parent / "specs" / "041-bteam-unified-pipeline-restructure"


def test_gate_contract_requires_external_approval_fields():
    schema = json.loads(
        (FEATURE / "contracts" / "deployment_gate_contract.json").read_text(
            encoding="utf-8"
        )
    )
    required = schema["allOf"][0]["then"]["required"]
    assert {"approved_by", "approval_authority", "approval_reference"}.issubset(
        required
    )


def test_green_compose_is_separate_and_has_no_fixed_container_name():
    compose = (ROOT / "docker-compose.green.yml").read_text(encoding="utf-8")
    assert "bteam-green" in compose
    assert "container_name:" not in compose
