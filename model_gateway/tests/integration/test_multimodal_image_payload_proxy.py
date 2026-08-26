"""
tests/integration/test_multimodal_image_payload_proxy.py
==============================================================================
Integration tests for OpenAI-compatible multimodal image payload proxy routing
and 25MB HTTP payload body size limit defense (FR-003, FR-005, SC-002).
==============================================================================
"""

import json
import pytest
from httpx import AsyncClient, ASGITransport
from src.api.main import app


@pytest.fixture
def mock_llama_env(monkeypatch):
    """Fixture enabling MOCK_LLAMA_SERVER environment variable for offline proxy testing."""
    monkeypatch.setenv("MOCK_LLAMA_SERVER", "1")


@pytest.mark.asyncio
async def test_multimodal_base64_image_payload_proxy(mock_llama_env):
    """Verify OpenAI-compatible Data URL Base64 image payload is successfully reverse proxied (200 OK)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "model": "qwen3.5-9b-vision",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this sample image."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 100
        }
        response = await client.post("/v1/chat/completions", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "chat.completion"
        assert data["model"] == "qwen3.5-9b-vision"
        assert len(data["choices"]) > 0


@pytest.mark.asyncio
async def test_multimodal_http_url_image_payload_proxy(mock_llama_env):
    """Verify OpenAI-compatible HTTP image URL payload is successfully reverse proxied (200 OK)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "model": "gemma4-e2b",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What is in this image?"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "https://example.com/sample_image.png"
                            }
                        }
                    ]
                }
            ]
        }
        response = await client.post("/v1/chat/completions", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["model"] == "gemma4-e2b"


@pytest.mark.asyncio
async def test_25mb_payload_size_limit_returns_413(mock_llama_env):
    """Verify HTTP POST body exceeding 25MB returns HTTP 413 Payload Too Large (FR-005)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a payload larger than 25MB (e.g., 26MB string)
        large_base64 = "A" * (26 * 1024 * 1024)
        payload = {
            "model": "qwen3.5-9b-vision",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Large payload test"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{large_base64}"}
                        }
                    ]
                }
            ]
        }
        response = await client.post("/v1/chat/completions", json=payload)
        assert response.status_code == 413
        assert "Payload Too Large" in response.text
