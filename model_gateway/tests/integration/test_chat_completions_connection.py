"""
Integration test for Chat Completions API connection drop & protocol errors (T006).
Ensures POST /v1/chat/completions responds without triggering peer closed connection or h11.LocalProtocolError.
"""

import pytest
import httpx
from src.api.main import app


@pytest.mark.asyncio
async def test_chat_completions_mock_connection():
    """Test Chat Completions proxy endpoint when MOCK_LLAMA_SERVER is enabled."""
    import os
    from src.core.llama_manager import llama_manager
    from src.core.process_manager import ProcessStatusEnum
    os.environ["MOCK_LLAMA_SERVER"] = "1"
    llama_manager.state = ProcessStatusEnum.READY
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "qwen3.5-4b",
                "messages": [{"role": "user", "content": "안녕하세요!"}]
            },
            headers={"Connection": "close"}
        )
        assert response.status_code == 200
        # Verify Content-Length is omitted or matches byte count
        if "content-length" in response.headers:
            assert int(response.headers["content-length"]) == len(response.content)
