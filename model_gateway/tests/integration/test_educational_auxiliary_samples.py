"""
Integration test for Educational Auxiliary Samples (Embedding & Reranking) (T010).
Verifies payload structures and endpoint responses for sample_03_embedding and sample_04_reranking.
"""

import pytest
import httpx
from src.api.main import app


@pytest.mark.asyncio
async def test_educational_embedding_and_rerank_payload():
    """Verify standard dict payloads on /embedding and /rerank endpoints."""
    import os
    os.environ["MOCK_LLAMA_SERVER"] = "1"
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Embedding payload check
        emb_resp = await client.post("/embedding", json={"input": ["테스트 문장입니다."]})
        assert emb_resp.status_code == 200
        emb_json = emb_resp.json()
        assert "data" in emb_json
        assert len(emb_json["data"]) > 0

        # Rerank payload check
        rerank_resp = await client.post(
            "/rerank",
            json={"query": "인공지능", "documents": ["AI 서비스 개발", "날씨 예보"]}
        )
        assert rerank_resp.status_code == 200
        rerank_json = rerank_resp.json()
        assert "results" in rerank_json
        assert len(rerank_json["results"]) > 0
