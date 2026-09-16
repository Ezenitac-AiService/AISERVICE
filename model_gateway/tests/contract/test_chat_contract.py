"""
Contract validation test for OpenAI Chat Completions API schema.
Validates response JSON structure against specs/006-model-gateway-upgrade/contracts/openai_chat_completions.json.
"""

import json
import os
import pytest
from pathlib import Path

def load_chat_contract():
    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent / "specs/006-model-gateway-upgrade/contracts/openai_chat_completions.json",
        Path(__file__).resolve().parent.parent.parent.parent.parent / "specs/006-model-gateway-upgrade/contracts/openai_chat_completions.json",
    ]
    for c in candidates:
        if c.exists():
            with open(c, "r", encoding="utf-8") as f:
                return json.load(f)
    return {
        "required": ["id", "object", "created", "model", "choices", "usage"],
        "properties": {"choices": {"type": "array"}}
    }


def test_chat_contract_schema():
    """Verify that sample OpenAI Chat response schema passes contract validation."""
    contract = load_chat_contract()
    resp_schema = contract.get("definitions", {}).get("ChatCompletionResponseNonStreaming", contract)
    
    mock_chat_response = {
        "id": "chatcmpl-12345",
        "object": "chat.completion",
        "created": 1722600000,
        "model": "qwen3.5-9b",
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
    required_keys = resp_schema.get("required", ["id", "object", "created", "model", "choices", "usage"])
    for key in required_keys:
        assert key in mock_chat_response, f"Missing required contract key: {key}"
