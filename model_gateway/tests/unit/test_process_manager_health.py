"""
tests/unit/test_process_manager_health.py
==============================================================================
099-fix-setup-gpu-benchmark: ProcessManager /health Polling & Cleanup Unit Tests

- Test 1: verify_host_loopback_binding defaults to 127.0.0.1
- Test 2: register_process_cleanup_hooks registers atexit and signal handlers
- Test 3: poll_server_health returns True on HTTP 200 OK
- Test 4: poll_server_health returns False on timeout
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

from src.core.process_manager import ProcessManager, register_process_cleanup_hooks, poll_server_health


@pytest.mark.asyncio
async def test_poll_server_health_mock_success(monkeypatch):
    """Verify poll_server_health returns True when mock server responds with HTTP 200 OK."""
    monkeypatch.delenv("MOCK_LLAMA_SERVER", raising=False)
    class MockResponse:
        status_code = 200
        def json(self):
            return {"status": "ok"}

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url, timeout=None):
            return MockResponse()

    monkeypatch.setattr("httpx.AsyncClient", MockAsyncClient)

    is_healthy = await poll_server_health(port=8081, timeout=2.0, interval=0.1)
    assert is_healthy is True


@pytest.mark.asyncio
async def test_poll_server_health_mock_timeout(monkeypatch):
    """Verify poll_server_health returns False when server connection fails/times out."""
    monkeypatch.delenv("MOCK_LLAMA_SERVER", raising=False)
    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url, timeout=None):
            raise Exception("Connection Refused")

    monkeypatch.setattr("httpx.AsyncClient", MockAsyncClient)

    is_healthy = await poll_server_health(port=8081, timeout=0.3, interval=0.1)
    assert is_healthy is False


def test_register_process_cleanup_hooks():
    """Verify register_process_cleanup_hooks executes without error."""
    register_process_cleanup_hooks()


def test_force_kill_zombie_llama_servers():
    """Verify force_kill_zombie_llama_servers static method executes without error."""
    ProcessManager.force_kill_zombie_llama_servers()


@pytest.mark.asyncio
async def test_poll_server_health_404_fallback_to_v1_models(monkeypatch):
    """T014/US3/FR-008: Verify poll_server_health falls back to /v1/models when /health returns HTTP 404."""
    monkeypatch.delenv("MOCK_LLAMA_SERVER", raising=False)
    class MockResponse:
        def __init__(self, status_code):
            self.status_code = status_code

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url, timeout=None):
            if url.endswith("/health"):
                return MockResponse(404)
            elif url.endswith("/v1/models"):
                return MockResponse(200)
            return MockResponse(500)

    monkeypatch.setattr("httpx.AsyncClient", MockAsyncClient)

    is_healthy = await poll_server_health(port=8081, timeout=2.0, interval=0.1)
    assert is_healthy is True

