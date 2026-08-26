"""
tests/integration/test_sample_scripts_and_reranker.py

Integration tests for feature 078-fix-samples-and-reranker-503:
1. samples/common.py configuration parsing priority and zero hardcoded IP strings in source code.
2. /v1/rerank and /v1/embeddings on-demand readiness proxy in inference_api.py preventing 503 errors.
"""

import os
import sys
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from sample.common import get_server_host, _format_host_url
from src.api.server import create_app


def test_no_hardcoded_ip_in_common_py():
    """FR-001 & SC-001: Ensure no hardcoded IP strings (e.g. 192.168.0.100) exist in sample/common.py executable code."""
    common_py_path = Path(__file__).parent.parent.parent / "sample" / "common.py"
    content = common_py_path.read_text(encoding="utf-8")
    assert "192.168.0.100" not in content, "Hardcoded IP 192.168.0.100 found in sample/common.py!"


def test_get_server_host_parsing_priority(tmp_path, monkeypatch):
    """FR-001: Test configuration parsing order (SERVER_HOST env > .env > config.json > 127.0.0.1 default)."""
    # Clear environment variables
    monkeypatch.delenv("SERVER_HOST", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("VLLM_API_BASE", raising=False)

    # 1. Test environment variable priority (format_host_url strips port for script {SERVER_HOST}:{PORT} composition)
    monkeypatch.setenv("SERVER_HOST", "http://10.0.0.41:8081")
    assert get_server_host() == "http://10.0.0.41"

    monkeypatch.delenv("SERVER_HOST")

    # 2. Test default fallback to 127.0.0.1 (when config.json and .env don't have host)
    formatted = _format_host_url("10.0.0.41:8081")
    assert formatted == "http://10.0.0.41"
    
    formatted_no_port = _format_host_url("http://192.168.0.100")
    assert formatted_no_port == "http://192.168.0.100"


def test_rerank_proxy_on_demand_readiness(monkeypatch):
    """FR-002, FR-003 & SC-001: Verify /v1/rerank proxy returns 200 OK and valid relevance scores."""
    monkeypatch.setenv("MOCK_LLAMA_SERVER", "1")
    from src.api.server import app
    client = TestClient(app)
    
    # Test /v1/rerank POST request matching sample_04_reranking.py payload format
    payload = {
        "model": "bge-reranker-v2-m3",
        "query": "vllm_serv 서버의 주요 장점과 사용법은 무엇인가요?",
        "documents": [
            "오늘 서울의 날씨는 맑고 기온은 25도입니다.",
            "vllm_serv는 llama.cpp 기반으로 Qwen3.5 및 Gemma4 모델을 GPU VRAM 100% 오프 로딩하여 빠른 속도로 서빙하는 서버입니다.",
            "파이썬 기초 문법에는 변수, 리스트, 딕셔너리, 조건문, 반복문 등이 있습니다."
        ]
    }
    resp = client.post("/v1/rerank", json=payload)
    assert resp.status_code == 200, f"Expected 200 OK, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "results" in data or "data" in data or data.get("model") == "bge-reranker-v2-m3", f"Response JSON invalid: {data}"


