from __future__ import annotations

import sys
from pathlib import Path
from typing import AsyncGenerator
import pytest
import pytest_asyncio
import httpx

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "packages" / "core"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


@pytest_asyncio.fixture
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Loop-isolated httpx.AsyncClient fixture for async contract/integration testing."""
    async with httpx.AsyncClient(
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=30, keepalive_expiry=60.0),
        timeout=httpx.Timeout(10.0, connect=5.0),
    ) as client:
        yield client
