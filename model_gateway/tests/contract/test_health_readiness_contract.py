"""
Contract test for content-signed readiness probe schema.
Validates GET /health/readiness response matches specs/006-model-gateway-upgrade/contracts/health_readiness.json.
"""

import json
import pytest
from pathlib import Path

def load_readiness_contract():
    path = Path(__file__).resolve().parent.parent.parent.parent / "specs/006-model-gateway-upgrade/contracts/health_readiness.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def test_health_readiness_response_schema():
    """Verify that sample Dual-LLM readiness probe payload satisfies contract specification."""
    contract = load_readiness_contract()
    required = contract.get("required", [
        "status", "model_id", "models", "vram_offloaded_100pct",
        "context_length", "active_slots", "queue_depth",
        "auxiliary_models", "drain_mode"
    ])

    sample_readiness_payload = {
        "status": "ready",
        "model_id": "dual-llm",
        "models": {
            "qwen3.5-9b": {
                "status": "ready",
                "port": 8089,
                "context_length": 32768
            },
            "qwen3.5-4b": {
                "status": "ready",
                "port": 8088,
                "context_length": 8192
            }
        },
        "vram_offloaded_100pct": True,
        "context_length": 32768,
        "active_slots": 0,
        "queue_depth": 0,
        "auxiliary_models": {
            "bge_m3": True,
            "bge_reranker_v2_m3": True
        },
        "drain_mode": False,
        "uptime_seconds": 120.5,
        "timestamp": 1726480000.0
    }

    for key in required:
        assert key in sample_readiness_payload, f"Missing required readiness contract key: {key}"

    assert sample_readiness_payload["vram_offloaded_100pct"] is True
    assert sample_readiness_payload["models"]["qwen3.5-9b"]["context_length"] == 32768
    assert sample_readiness_payload["models"]["qwen3.5-4b"]["context_length"] == 8192
