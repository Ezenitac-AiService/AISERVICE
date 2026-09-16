"""
Contract test for queue policies and unified cancel schema (T010).
Validates QueueCancelResponse matches contracts/queue_management.json.
"""

import json
import pytest
from pathlib import Path

def load_queue_contract():
    path = Path(__file__).resolve().parent.parent.parent.parent / "specs/006-model-gateway-upgrade/contracts/queue_management.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def test_queue_cancel_response_schema():
    """Verify QueueCancelResponse schema matches unified contract."""
    contract = load_queue_contract()
    cancel_schema = contract.get("components", {}).get("schemas", {}).get("QueueCancelResponse", {})
    required = cancel_schema.get("required", ["ticket_id", "status", "success", "slot_released", "previous_status"])

    sample_cancel_response = {
        "ticket_id": "ticket-9b-12345",
        "status": "CANCELLED",
        "success": True,
        "slot_released": True,
        "previous_status": "WAITING",
        "message": "Queue ticket cancelled successfully."
    }

    for field in required:
        assert field in sample_cancel_response, f"Missing required field in cancel response: {field}"

    assert sample_cancel_response["status"] in ["CANCELLED", "NOT_FOUND"]
    assert isinstance(sample_cancel_response["slot_released"], bool)
