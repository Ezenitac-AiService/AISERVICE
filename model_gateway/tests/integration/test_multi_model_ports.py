"""
Integration test for Multi-Model Serving Ports (8081, 8090, 8091) in vllm_serv (T014).
Verifies health and proxy routing to Embedding (8090) and Reranker (8091) auxiliary instances.
"""

import pytest
import httpx
from src.api.main import app


@pytest.mark.asyncio
async def test_auxiliary_embedding_reranker_proxy():
    """Verify reverse-proxy routing to /embedding and /rerank when MOCK_LLAMA_SERVER is set."""
    import os
    os.environ["MOCK_LLAMA_SERVER"] = "1"
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Embedding endpoint check
        emb_resp = await client.post("/embedding", json={"input": ["테스트 문장입니다."]})
        assert emb_resp.status_code == 200
        emb_json = emb_resp.json()
        assert "data" in emb_json

        # Rerank endpoint check
        rerank_resp = await client.post(
            "/rerank",
            json={"query": "AI 기술", "documents": ["인공지능 발전", "날씨 정보"]}
        )
        assert rerank_resp.status_code == 200
        rerank_json = rerank_resp.json()
        assert "results" in rerank_json
