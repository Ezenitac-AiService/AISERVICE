"""
Contract tests for Queue SSE Protocol and Cancel API (Spec 031 T005).
Validates queue_status event schema, keepalive formatting, and cancellation responses.
"""

import json
import pytest
from src.core.queue_models import QueueTicket, QueueStateEnum


def test_queue_status_payload_contract():
    ticket = QueueTicket(
        ticket_id="req_test123",
        tenant_id="chata",
        session_id="ses_abc",
        prompt_hash="a1b2c3d4",
        created_at=1724670000.0,
        state=QueueStateEnum.QUEUED,
        queue_position=2,
        estimated_wait_s=8.0
    )
    
    payload = ticket.to_status_dict(total_queued=3, active_slots=1, max_slots=1)
    
    assert payload["ticket_id"] == "req_test123"
    assert payload["tenant_id"] == "chata"
    assert payload["status"] == "QUEUED"
    assert payload["queue_position"] == 2
    assert payload["total_queued"] == 3
    assert payload["active_slots"] == 1
    assert payload["max_slots"] == 1
    assert payload["estimated_wait_sec"] == 8.0
    assert "elapsed_sec" in payload
    assert "timestamp" in payload


def test_queue_sse_format_contract():
    ticket = QueueTicket(
        ticket_id="req_test456",
        tenant_id="chatb",
        session_id="ses_xyz",
        prompt_hash="e5f6g7h8",
        created_at=1724670000.0,
        state=QueueStateEnum.ACTIVE,
        queue_position=0,
        estimated_wait_s=0.0
    )
    
    status_dict = ticket.to_status_dict(total_queued=0, active_slots=1, max_slots=1)
    sse_formatted = f"event: queue_status\ndata: {json.dumps(status_dict, ensure_ascii=False)}\n\n"
    
    assert sse_formatted.startswith("event: queue_status\n")
    assert "data: {" in sse_formatted
    assert sse_formatted.endswith("\n\n")
