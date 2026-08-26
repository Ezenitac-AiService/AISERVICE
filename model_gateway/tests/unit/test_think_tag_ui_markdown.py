"""
Unit Test Suite for AI Playground Think Tag UI Modes, Markdown & Chat Sessions API (048-think-tag-ui-markdown).
Strict Anti-Mock Real Execution per Constitution v1.5.2.
"""

import pytest
from fastapi.testclient import TestClient
from src.api.server import app
from src.core.metrics_db import metrics_db

client = TestClient(app)


def test_playground_sessions_db_crud():
    """T002, T003, T009 & FR-007, FR-008: Test SQLite playground_sessions and messages CRUD operations."""
    session_id = f"sess_test_{int(metrics_db._get_connection().execute('SELECT COUNT(*) FROM api_key_logs').fetchone()[0]) + 100}"
    
    # 1. Create session
    metrics_db.create_playground_session(session_id, "Test Session Title")
    
    # 2. Add messages
    metrics_db.add_playground_message(session_id, "user", "Hello AI", None)
    metrics_db.add_playground_message(session_id, "assistant", "Hello! How can I help?", "Thinking process text...")
    
    # 3. List sessions
    sessions = metrics_db.list_playground_sessions()
    assert any(s["id"] == session_id for s in sessions)
    
    # 4. Get messages
    msgs = metrics_db.get_playground_messages(session_id)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["thinking_process"] == "Thinking process text..."
    
    # 5. Delete session
    metrics_db.delete_playground_session(session_id)
    sessions_after = metrics_db.list_playground_sessions()
    assert not any(s["id"] == session_id for s in sessions_after)


def test_playground_sessions_api_endpoints():
    """T003, T009 & FR-008: Test REST API endpoints for playground session management."""
    # Create via POST
    res_create = client.post("/dashboard/api/playground/sessions", json={"title": "REST API Test Session"})
    assert res_create.status_code == 200
    sess_data = res_create.json()
    assert "id" in sess_data
    session_id = sess_data["id"]
    
    # List via GET
    res_list = client.get("/dashboard/api/playground/sessions")
    assert res_list.status_code == 200
    assert any(s["id"] == session_id for s in res_list.json())
    
    # Add message
    client.post(f"/dashboard/api/playground/sessions/{session_id}/messages", json={
        "role": "user",
        "content": "Test prompt",
        "thinking_process": None
    })
    
    # Fetch messages
    res_msgs = client.get(f"/dashboard/api/playground/sessions/{session_id}/messages")
    assert res_msgs.status_code == 200
    assert len(res_msgs.json()) >= 1
    assert res_msgs.json()[0]["content"] == "Test prompt"
    
    # Delete via DELETE
    res_del = client.delete(f"/dashboard/api/playground/sessions/{session_id}")
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "success"


def test_playground_stream_endpoint():
    """Test SSE real-time streaming endpoint /dashboard/api/playground/stream."""
    res = client.post("/dashboard/api/playground/stream", json={
        "prompt": "Hello stream test",
        "system_prompt": "You are a test bot",
        "max_tokens": 100
    })
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]
    assert "[DONE]" in res.text or "data:" in res.text
