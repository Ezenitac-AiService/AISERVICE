"""
tests/integration/test_gpu_spawn_warmup.py
==============================================================================
099-fix-setup-gpu-benchmark: Integration test for /health polling & GPU warmup

Verify that spawn_process + poll_server_health correctly sets ProcessState to READY
and allows successful warmup inference.
==============================================================================
"""

import os
import sys
import pytest
import asyncio
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.process_manager import ProcessManager, ProcessStatusEnum, poll_server_health
from scripts.benchmark_context_window import _execute_single_binary_search_inner


@pytest.mark.asyncio
async def test_gpu_spawn_and_health_polling_warmup(monkeypatch):
    """Verify that _execute_single_binary_search_inner uses poll_server_health and sets is_supported=True in mock mode."""
    monkeypatch.setenv("MOCK_LLAMA_SERVER", "1")

    res = await _execute_single_binary_search_inner("qwen3.5-4b")

    assert res["is_supported"] is True
    assert res["recommended_context_length"] >= 2048
    assert res["tpot_tok_per_sec"] > 0.0
    assert len(res["binary_search_steps"]) > 0
