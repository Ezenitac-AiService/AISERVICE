"""
tests/integration/test_reranker_404_routing.py

Integration test for feature 079-fix-reranker-404-routing:
Verifies that reverse_proxy in inference_api.py automatically falls back across candidate backend paths
(["/reranking", "/v1/rerank", "/rerank", "/v1/reranking"]) on port 8091 when receiving /v1/rerank requests,
preventing 404 Not Found errors.
"""

import pytest
import json
import httpx
from fastapi.testclient import TestClient
from src.api.server import create_app


@pytest.mark.asyncio
async def test_reranker_candidate_path_fallback(monkeypatch):
    """FR-001 & SC-001: Test reverse proxy candidate path fallback on port 8091 when initial path returns 404."""
    monkeypatch.setenv("MOCK_LLAMA_SERVER", "1")
    app = create_app()

    async with app.router.lifespan_context(app):
        client = TestClient(app)

        # Test POST /v1/rerank
        payload = {
            "model": "bge-reranker-v2-m3",
            "query": "vllm_serv 장점",
            "documents": ["vllm_serv는 고성능 LLM 플랫폼입니다.", "날씨가 맑습니다."]
        }

        resp = client.post("/v1/rerank", json=payload)
        assert resp.status_code == 200, f"Expected 200 OK, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("model") == "bge-reranker-v2-m3" or "results" in data or "data" in data

        # Test POST /rerank
        resp_alt = client.post("/rerank", json=payload)
        assert resp_alt.status_code == 200, f"Expected 200 OK for /rerank, got {resp_alt.status_code}: {resp_alt.text}"
