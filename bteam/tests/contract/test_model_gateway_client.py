"""
Contract verification tests for Model Gateway (port 8081) and AiGatewayClient.
Validates non-blocking async HTTP/1.1 communication for:
- BGE-M3 (/v1/embeddings)
- BGE-Reranker-v2-m3 (/v1/rerank)
- Qwen 3.5 (/v1/chat/completions stream)
"""

import json
import pytest
import httpx
from oliview_core.config import CoreSettings
from oliview_core.client import AiGatewayClient


@pytest.fixture
def local_settings():
    """Settings configured for local host gateway testing."""
    return CoreSettings(
        LLM_BASE_URL="http://127.0.0.1:8081/v1",
        EMBEDDING_BASE_URL="http://127.0.0.1:8081/v1",
        RERANK_BASE_URL="http://127.0.0.1:8081/v1",
        MODEL_GATEWAY_HEALTH_URL="http://127.0.0.1:8081/health",
        CHROMA_SERVER_HOST="127.0.0.1",
        CHROMA_SERVER_PORT=8000,
        embedding_model="bge-m3",
        rerank_model="bge-reranker-v2-m3",
        fast_llm_model="qwen3.5-4b",
        synthesis_llm_model="qwen3.5-4b",
        timeout_search_sec=5.0,
        timeout_rerank_sec=5.0,
        timeout_llm_sec=15.0,
    )


@pytest.mark.asyncio
async def test_gateway_health_contract(http_client: httpx.AsyncClient, local_settings: CoreSettings):
    """Ensure model-gateway is healthy and responsive."""
    resp = await http_client.get(local_settings.MODEL_GATEWAY_HEALTH_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "alive"


@pytest.mark.asyncio
async def test_async_embedding_contract(http_client: httpx.AsyncClient, local_settings: CoreSettings):
    """Verify BGE-M3 embedding contract returns 1024-dim vectors asynchronously."""
    url = f"{local_settings.embed_endpoint}/embeddings"
    payload = {
        "model": local_settings.embedding_model,
        "input": ["차앤박 프로폴리스 앰플 수분감", "흡수력이 빠르고 산뜻함"],
    }
    resp = await http_client.post(url, json=payload)
    assert resp.status_code == 200
    res_data = resp.json()
    assert "data" in res_data
    assert len(res_data["data"]) == 2
    vec0 = res_data["data"][0]["embedding"]
    assert len(vec0) == 1024
    assert isinstance(vec0[0], float)


@pytest.mark.asyncio
async def test_async_reranker_contract(http_client: httpx.AsyncClient, local_settings: CoreSettings):
    """Verify BGE-Reranker-v2-m3 contract returns relevance scores asynchronously."""
    url = f"{local_settings.rerank_endpoint}/rerank"
    payload = {
        "model": local_settings.rerank_model,
        "query": "수분감과 흡수력",
        "documents": [
            "수분감이 풍부하고 빠르게 흡수됩니다.",
            "유분기가 많고 끈적거려서 답답해요.",
        ],
    }
    resp = await http_client.post(url, json=payload)
    assert resp.status_code == 200
    res_data = resp.json()
    results = res_data.get("results") or res_data.get("data")
    assert results is not None
    assert len(results) == 2
    # Document 0 (relevant) should have higher raw logit than Document 1 (irrelevant)
    score0 = results[0]["relevance_score"]
    score1 = results[1]["relevance_score"]
    assert score0 > score1


@pytest.mark.asyncio
async def test_async_llm_stream_contract(http_client: httpx.AsyncClient, local_settings: CoreSettings):
    """Verify LLM SSE stream returns valid chunks via aiter_lines() asynchronously."""
    url = f"{local_settings.llm_endpoint}/chat/completions"
    payload = {
        "model": local_settings.fast_llm_model,
        "messages": [
            {"role": "user", "content": "안녕하세요. '확인'이라고 한 단어만 답해주세요."}
        ],
        "max_tokens": 16,
        "stream": True,
    }
    tokens = []
    async with http_client.stream("POST", url, json=payload) as resp:
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            line = line.strip()
            if not line or line.startswith(":"):
                continue
            if line.startswith("data:"):
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    break
                chunk = json.loads(data_str)
                delta = chunk["choices"][0].get("delta", {})
                content = delta.get("content") or delta.get("reasoning_content")
                if content:
                    tokens.append(content)

    assert len(tokens) > 0


@pytest.mark.asyncio
async def test_aigateway_client_async_methods(http_client: httpx.AsyncClient, local_settings: CoreSettings):
    """Verify AiGatewayClient non-blocking async methods with injected client."""
    client = AiGatewayClient(settings=local_settings, client=http_client)

    # 1. aembed
    embeddings = await client.aembed(["차앤박 프로폴리스 앰플"])
    assert len(embeddings) == 1
    assert len(embeddings[0]) == 1024

    # 2. arerank
    scores = await client.arerank(
        query="보습력",
        documents=["촉촉하고 보습이 잘 돼요", "전혀 보습이 안 돼요"]
    )
    assert scores is not None
    assert len(scores) == 2
    assert scores[0] > scores[1]

    # 3. agenerate_stream
    stream_tokens = []
    async for token in client.agenerate_stream(prompt="1+1은? 숫자만 답해줘", max_tokens=10):
        stream_tokens.append(token)
    assert len(stream_tokens) > 0


@pytest.mark.asyncio
async def test_structured_json_completion_contract(http_client: httpx.AsyncClient, local_settings: CoreSettings):
    """Verify Model Gateway structured JSON completion contract returns finish_reason == 'stop' and valid JSON (T029)."""
    url = f"{local_settings.llm_endpoint}/chat/completions"
    payload = {
        "model": local_settings.fast_llm_model,
        "messages": [
            {"role": "user", "content": 'Return a JSON object with key "status" and value "ready".'}
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 100,
        "stream": False,
    }
    resp = await http_client.post(url, json=payload, timeout=15.0)
    assert resp.status_code == 200
    res_data = resp.json()
    assert "choices" in res_data
    assert len(res_data["choices"]) > 0
    choice = res_data["choices"][0]
    assert choice.get("finish_reason") == "stop"
    content = choice.get("message", {}).get("content", "")
    assert content
    parsed = json.loads(content)
    assert isinstance(parsed, dict)
    assert parsed.get("status") == "ready"

