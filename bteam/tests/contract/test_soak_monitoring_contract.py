import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC_042 = ROOT.parent / "specs" / "042-bteam-production-cutover"


def test_soak_monitoring_contract_schema():
    schema = json.loads(
        (SPEC_042 / "contracts" / "soak_monitoring_contract.json").read_text(
            encoding="utf-8"
        )
    )
    required = schema["required"]
    assert {
        "soak_duration_hours",
        "probe_interval_seconds",
        "sla_thresholds",
        "rollback_triggers",
    }.issubset(required)

    sla_props = schema["properties"]["sla_thresholds"]["properties"]
    assert sla_props["demo_general_rag_max_seconds"]["maximum"] == 20.0
    assert sla_props["prod_chatbot_p95_max_seconds"]["maximum"] == 5.0

    triggers = schema["properties"]["rollback_triggers"]["properties"]
    assert triggers["max_tolerated_http_5xx"]["enum"] == [0]
    assert triggers["max_consecutive_probe_failures"]["enum"] == [1]
    assert triggers["max_consecutive_sla_violations"]["enum"] == [1]
