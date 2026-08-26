"""
Contract validation test for OpenAI Chat Completions API schema (T007).
Validates response JSON structure against contracts/chat-completion-contract.json.
"""

import json
import os
import pytest
CONTRACT_PATH = os.path.join(
    os.path.dirname(__file__),
    "../../specs/073-fix-chat-peer-closed/contracts/chat-completion-contract.json"
)


def load_chat_contract():
    assert os.path.exists(CONTRACT_PATH), f"Contract file not found: {CONTRACT_PATH}"
    with open(CONTRACT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_chat_contract_schema():
    """Verify that sample OpenAI Chat response schema passes contract validation."""
    contract_schema = load_chat_contract()
    assert "properties" in contract_schema
    
    mock_chat_response = {
        "id": "chatcmpl-12345",
        "object": "chat.completion",
        "created": 1722600000,
        "model": "qwen3.5-4b",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "안녕하세요! 무엇을 도와드릴까요?"
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 8,
            "total_tokens": 20
        }
    }
    
    # Validate required top-level keys match contract schema
    required_keys = contract_schema.get("required", [])
    for key in required_keys:
        assert key in mock_chat_response, f"Missing required contract key: {key}"
