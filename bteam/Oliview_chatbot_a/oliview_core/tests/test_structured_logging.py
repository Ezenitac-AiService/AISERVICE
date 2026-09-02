import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator, ValidationError

CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "specs" / "048-anti-fictional-user-and-citation-fidelity" / "contracts"


def get_log_schema() -> dict:
    path = CONTRACTS_DIR / "structured_log_contract.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_structured_log_contract_valid_entry():
    schema = get_log_schema()
    validator = Draft202012Validator(schema)

    valid_log = {
        "timestamp": "2026-09-02T15:30:00Z",
        "correlation_id": "12345678-1234-5678-1234-567812345678",
        "service": "chat_a",
        "event": "request_completed",
        "latency_ms": 320,
        "model_invoked": True,
        "abstained": False,
        "redaction_applied": True,
        "guardrail_counts": {
            "persona_removed": 0,
            "quotes_removed": 0,
            "citations_removed": 0,
            "polarity_blocked": 0,
            "injection_blocked": 0,
            "pii_redacted": 1,
        },
    }
    validator.validate(valid_log)


def test_structured_log_contract_prohibits_raw_sensitive_fields():
    schema = get_log_schema()
    validator = Draft202012Validator(schema)

    invalid_log_with_query = {
        "timestamp": "2026-09-02T15:30:00Z",
        "correlation_id": "12345678-1234-5678-1234-567812345678",
        "service": "chat_a",
        "event": "request_completed",
        "latency_ms": 320,
        "model_invoked": True,
        "abstained": False,
        "redaction_applied": False,
        "query": "비밀 질문 내용",  # forbidden by additionalProperties: false
        "guardrail_counts": {
            "persona_removed": 0,
            "quotes_removed": 0,
            "citations_removed": 0,
            "polarity_blocked": 0,
            "injection_blocked": 0,
            "pii_redacted": 0,
        },
    }
    with pytest.raises(ValidationError):
        validator.validate(invalid_log_with_query)


def test_structured_logging_module_red_gate():
    """RED GATE: Asserts that oliview_core.logging provides emit_structured_log.
    Fails until Phase 3 implementation."""
    try:
        from oliview_core.logging import emit_structured_log  # type: ignore
        assert callable(emit_structured_log)
    except (ImportError, AttributeError) as exc:
        pytest.fail(f"RED GATE: emit_structured_log not implemented in oliview_core.logging: {exc}")
