"""
Unit Test Suite for LLM Response <think> Tag Stripping & Parsing (047-think-tag-stripping).
Strict Anti-Mock Real Execution & TDD per Constitution v1.5.2.
"""

import time
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from src.api.server import app
from src.core.think_tag_parser import parse_think_tags, ThinkTagStreamFilter
from src.core.metrics_db import metrics_db

client = TestClient(app)


def test_think_tag_parser_unit():
    """T004 & FR-001, FR-006: Test think tag parser helper function with various outputs."""
    # 1. Standard closed think tag
    text1 = "<think>\nStep 1: Calculate 2+2.\nStep 2: Result is 4.\n</think>\n\nAnswer: 4"
    clean_text1, think_text1 = parse_think_tags(text1)
    assert clean_text1 == "Answer: 4"
    assert "Step 1: Calculate 2+2" in think_text1

    # 2. No think tag
    text2 = "Plain answer without reasoning."
    clean_text2, think_text2 = parse_think_tags(text2)
    assert clean_text2 == "Plain answer without reasoning."
    assert think_text2 is None

    # 3. Unclosed think tag (truncation scenario)
    text3 = "<think>\nReasoning started but tokens ran out..."
    clean_text3, think_text3 = parse_think_tags(text3)
    assert clean_text3 == "[Truncated during thinking process]"
    assert think_text3 == "Reasoning started but tokens ran out..."

    # 4. Parsing overhead assertion (<1ms)
    start_t = time.perf_counter()
    for _ in range(100):
        parse_think_tags(text1)
    elapsed_ms = (time.perf_counter() - start_t) * 1000.0 / 100
    assert elapsed_ms < 1.0, f"Overhead per call exceeded 1ms: {elapsed_ms:.4f}ms"


def test_think_tag_stream_filter():
    """FR-005: Test streaming state machine filter for real-time SSE stream."""
    stream_filter = ThinkTagStreamFilter()
    chunks = ["<think>", "\nAnalyzing prompt...", "\n</think>", "\n\nFinal ", "answer."]
    output_tokens = []
    for chunk in chunks:
        token = stream_filter.process_chunk(chunk)
        if token:
            output_tokens.append(token)
    
    full_output = "".join(output_tokens)
    assert "<think>" not in full_output
    assert "Analyzing prompt" not in full_output
    assert "Final answer." in full_output
    assert "Analyzing prompt..." in stream_filter.get_thinking_text()


def test_playground_response_thinking_process():
    """T005, T006 & FR-002, FR-007: Test playground API default max_tokens 1024 and thinking_process field."""
    mock_backend_response = MagicMock()
    mock_backend_response.status_code = 200
    mock_backend_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "<think>\nChecking capital of France...\n</think>\nParis is the capital of France."
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30
        }
    }

    with patch("src.api.routes.dashboard_api.check_llama_status", new_callable=AsyncMock) as mock_status, \
         patch("src.api.routes.inference_api._default_client.post", new_callable=AsyncMock) as mock_post:
        mock_status.return_value = True
        mock_post.return_value = mock_backend_response

        res = client.post(
            "/dashboard/api/playground",
            json={
                "prompt": "Capital of France?",
                "system_prompt": "You are helpful."
            }
        )
        assert res.status_code == 200
        data = res.json()
        assert data["text"] == "Paris is the capital of France."
        assert "thinking_process" in data
        assert data["thinking_process"] == "Checking capital of France..."

        # Verify max_tokens default 1024 was passed to backend
        assert mock_post.called
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["max_tokens"] == 1024


def test_playground_strip_think_tags_toggle():
    """T012, T013 & US3: Test strip_think_tags=False toggle parameter."""
    mock_backend_response = MagicMock()
    mock_backend_response.status_code = 200
    mock_backend_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "<think>\nThinking...\n</think>\nRaw answer"
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15}
    }

    with patch("src.api.routes.dashboard_api.check_llama_status", new_callable=AsyncMock) as mock_status, \
         patch("src.api.routes.inference_api._default_client.post", new_callable=AsyncMock) as mock_post:
        mock_status.return_value = True
        mock_post.return_value = mock_backend_response

        res = client.post(
            "/dashboard/api/playground",
            json={
                "prompt": "Hello",
                "strip_think_tags": False
            }
        )
        assert res.status_code == 200
        data = res.json()
        assert "<think>" in data["text"]


def test_audit_payload_viewer_thinking_text():
    """T009, T010 & US2: Test audit payload viewer API returning thinking_text."""
    metrics_db.log_request(
        api_key="test-key-047",
        endpoint="/dashboard/api/playground",
        status_code=200,
        prompt_tokens=10,
        completion_tokens=20,
        ttft_ms=30.0,
        tps=40.0,
        is_error=False,
        prompt_text="Solve 5x = 20",
        completion_text="x = 4",
        thinking_text="Divide 20 by 5 to get 4."
    )

    with metrics_db._get_connection() as conn:
        row = conn.execute("SELECT id FROM api_key_logs ORDER BY id DESC LIMIT 1").fetchone()
        log_id = row["id"]

    res = client.get(f"/dashboard/api/audit/payload/{log_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert "thinking_text" in body["payload"]
    assert body["payload"]["thinking_text"] == "Divide 20 by 5 to get 4."
