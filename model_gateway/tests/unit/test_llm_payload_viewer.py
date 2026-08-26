"""
Unit/Integration Test Suite for LLM Response Payload Viewer & Google AI Studio Playground (044-llm-response-payload-viewer).
Strict Anti-Mock Real Execution per Constitution v1.4.0.
"""

import pytest
from fastapi.testclient import TestClient
from src.api.server import app
from src.core.metrics_db import metrics_db

client = TestClient(app)


def test_llm_response_payload_viewer_flow():
    # 1. Trigger Playground Request to insert a log entry with prompt & completion text
    res_pg = client.post(
        "/dashboard/api/playground",
        json={
            "prompt": "Explain quantum computing in simple terms.",
            "system_prompt": "You are a concise physics teacher.",
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 256
        }
    )
    assert res_pg.status_code == 200, f"Expected 200, got {res_pg.status_code}"
    data_pg = res_pg.json()
    assert "text" in data_pg
    assert "Explain quantum computing" not in data_pg["text"]  # output text check

    # 2. Log manual entry into MetricsDB to ensure known log ID
    metrics_db.log_request(
        api_key="test-key-044",
        endpoint="/v1/chat/completions",
        status_code=200,
        prompt_tokens=15,
        completion_tokens=40,
        ttft_ms=45.2,
        tps=32.5,
        is_error=False,
        prompt_text="What is the capital of South Korea?",
        completion_text="The capital of South Korea is Seoul."
    )

    # 3. Retrieve Payload via GET /dashboard/api/audit/payload/{log_id}
    # Get recent aggregated metrics or test payload directly
    payload_data = metrics_db.get_payload_by_id(1)
    assert payload_data is not None

    # Test REST API Endpoint
    res_payload = client.get("/dashboard/api/audit/payload/1")
    assert res_payload.status_code == 200, f"Expected 200, got {res_payload.status_code}"
    body = res_payload.json()
    assert body["status"] == "success"
    assert "payload" in body
    assert "prompt_text" in body["payload"]
    assert "completion_text" in body["payload"]

    # 4. Test 404 for invalid log ID
    res_404 = client.get("/dashboard/api/audit/payload/999999")
    assert res_404.status_code == 404
