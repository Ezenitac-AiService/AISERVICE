"""
tests/integration/test_reranker_404_routing.py

Integration test for feature 079-fix-reranker-404-routing:
Verifies that reverse_proxy in inference_api.py automatically falls back across candidate backend paths
(["/reranking", "/v1/rerank", "/rerank", "/v1/reranking"]) on port 8091 when receiving /v1/rerank requests,
preventing 404 Not Found errors.
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from src.api.server import create_app
from src.core.process_manager import ProcessStatusEnum, ProcessState
from src.core.auxiliary_manager import auxiliary_manager


@pytest.mark.asyncio
async def test_reranker_candidate_path_fallback(monkeypatch):
    """FR-001 & SC-001: Test reverse proxy candidate path fallback on port 8091 when initial path returns 404."""
    auxiliary_manager.rerank_pm.state = ProcessState(status=ProcessStatusEnum.READY, port=8091)
    monkeypatch.setattr(auxiliary_manager, "ensure_rerank_resident", AsyncMock(return_value=auxiliary_manager.rerank_pm.state))

    mock_resp_404 = MagicMock()
    mock_resp_404.status_code = 404
    mock_resp_404.headers = {}
    mock_resp_404.aclose = AsyncMock()

    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_resp_200.headers = {"content-type": "application/json"}
    mock_resp_200.aclose = AsyncMock()

    async def aiter_raw():
        yield json.dumps({
            "model": "bge-reranker-v2-m3",
            "results": [{"index": 0, "relevance_score": 0.95}, {"index": 1, "relevance_score": 0.12}]
        }).encode("utf-8")

    mock_resp_200.aiter_raw = aiter_raw

    mock_client = MagicMock()
    mock_client.build_request = MagicMock()
    # First candidate path returns 404, second returns 200
    mock_client.send = AsyncMock(side_effect=[mock_resp_404, mock_resp_200, mock_resp_404, mock_resp_200])

    app = create_app()

    with patch("src.api.routes.inference_api._get_http_client", return_value=mock_client):
        client = TestClient(app)

        payload = {
            "model": "bge-reranker-v2-m3",
            "query": "vllm_serv 장점",
            "documents": ["vllm_serv는 고성능 LLM 플랫폼입니다.", "날씨가 맑습니다."]
        }

        resp = client.post("/v1/rerank", json=payload)
        assert resp.status_code == 200, f"Expected 200 OK, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("model") == "bge-reranker-v2-m3" or "results" in data or "data" in data

        resp_alt = client.post("/rerank", json=payload)
        assert resp_alt.status_code == 200, f"Expected 200 OK for /rerank, got {resp_alt.status_code}: {resp_alt.text}"

