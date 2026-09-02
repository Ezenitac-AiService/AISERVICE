"""
Unit tests for AiGatewayClient (Sync & Async).
"""

import sys
import os
from unittest.mock import MagicMock, patch

current_dir = os.path.dirname(os.path.abspath(__file__))
workspace_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
bteam_dir = os.path.join(workspace_root, "bteam")
if bteam_dir not in sys.path:
    sys.path.insert(0, bteam_dir)

from oliview_core.client import AiGatewayClient
from oliview_core.config import get_settings


def test_ai_gateway_client_endpoints():
    """Verify endpoint construction in client."""
    client = AiGatewayClient()
    settings = get_settings()
    assert client.settings.main_port == 8081
    assert "8090/v1" in client.settings.embed_endpoint
    assert "8091/v1" in client.settings.rerank_endpoint


def test_ai_gateway_client_generate_stream_sse_mock():
    """Verify generate_stream yields tokens using httpx without NameError."""
    client = AiGatewayClient()

    sse_lines = [
        ': keepalive\n',
        'data: {"choices": [{"delta": {"content": "촉촉한 "}}]}\n',
        'data: {"choices": [{"delta": {"content": "수분크림입니다."}}]}\n',
        'data: [DONE]\n'
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_lines.return_value = sse_lines

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__enter__.return_value = mock_resp
    mock_stream_ctx.__exit__.return_value = None

    mock_httpx_client = MagicMock()
    mock_httpx_client.stream.return_value = mock_stream_ctx
    mock_httpx_client.__enter__.return_value = mock_httpx_client
    mock_httpx_client.__exit__.return_value = None

    with patch("httpx.Client", return_value=mock_httpx_client):
        tokens = list(client.generate_stream(prompt="수분크림 추천해줘", system_prompt="시스템"))

    assert len(tokens) == 2
    assert "".join(tokens) == "촉촉한 수분크림입니다."


def test_ai_gateway_client_embed_live():
    """Verify live embedding against port 8090."""
    client = AiGatewayClient()
    embeddings = client.embed(["차앤박 프로폴리스 앰플"])
    assert len(embeddings) == 1
    assert len(embeddings[0]) > 0


def test_ai_gateway_client_rerank_live():
    """Verify live reranking against port 8091 (0.03s latency)."""
    client = AiGatewayClient()
    scores = client.rerank(
        query="보습력 좋은 앰플",
        documents=["차앤박 프로폴리스 앰플은 촉촉하고 수분감이 좋습니다.", "헤라 블랙쿠션은 커버력이 뛰어납니다."]
    )
    assert len(scores) == 2
    # Document 1 about 앰플 should score higher than Document 2 about 쿠션
    assert scores[0] >= scores[1]


if __name__ == "__main__":
    test_ai_gateway_client_endpoints()
    test_ai_gateway_client_generate_stream_sse_mock()
    test_ai_gateway_client_embed_live()
    test_ai_gateway_client_rerank_live()
    print("All AiGatewayClient unit tests passed successfully!")
