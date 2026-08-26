"""
Integration test for Educational Sample Scripts (074-educational-openai-samples) (T004).
Verifies that sample scripts run without Pydantic dependencies or protocol errors.
"""

import pytest
import httpx
from src.api.main import app


@pytest.mark.asyncio
async def test_educational_chat_dict_payload():
    """Verify standard Python dictionary payload on /v1/chat/completions."""
    import os
    os.environ["MOCK_LLAMA_SERVER"] = "1"
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Standard Python dict payload (no Pydantic models)
        payload = {
            "model": "qwen3.5-4b",
            "messages": [
                {"role": "system", "content": "친절한 AI 어시스턴트입니다."},
                {"role": "user", "content": "안녕하세요!"}
            ],
            "temperature": 0.3,
            "max_tokens": 100
        }
        response = await client.post("/v1/chat/completions", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "choices" in data
        assert len(data["choices"]) > 0
        assert "message" in data["choices"][0]
