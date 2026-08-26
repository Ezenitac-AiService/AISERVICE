"""
Integration test for Model Parameters (Temperature, Top_P, Stop Sequence) in vllm_serv (T011).
Verifies that stop sequence truncation and low temperature sampling execute without protocol error.
"""

import pytest
import httpx
from src.api.main import app


@pytest.mark.asyncio
async def test_stop_sequence_handling():
    """Verify stop sequence handling on Chat Completions endpoint."""
    import os
    os.environ["MOCK_LLAMA_SERVER"] = "1"
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "qwen3.5-4b",
                "messages": [{"role": "user", "content": "1부터 5까지 숫자를 세어주세요."}],
                "temperature": 0.0,
                "stop": ["3", "4"]
            },
            headers={"Connection": "close"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "choices" in data
        assert len(data["choices"]) > 0
