"""
Integration test for Educational Model Parameters Sample (T007).
Verifies that sample_02_model_params payloads (temperature, top_p, stop) function cleanly.
"""

import pytest
import httpx
from src.api.main import app


@pytest.mark.asyncio
async def test_educational_model_params_payload():
    """Test model parameter control payload structure with mock backend."""
    import os
    os.environ["MOCK_LLAMA_SERVER"] = "1"
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        payload = {
            "model": "qwen3.5-4b",
            "messages": [{"role": "user", "content": "파라미터 테스트"}],
            "temperature": 0.0,
            "top_p": 0.9,
            "stop": ["\n"]
        }
        response = await client.post("/v1/chat/completions", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "choices" in data
