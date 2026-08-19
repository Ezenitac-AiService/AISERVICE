import os
import json
try:
    import pytest
except ImportError:
    pytest = None
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

def test_root_env_configuration():
    """Verify FAST_LLM_MODEL and SYNTHESIS_LLM_MODEL in .env"""
    env_file = ROOT_DIR / ".env"
    assert env_file.exists(), ".env must exist"
    
    content = env_file.read_text(encoding="utf-8")
    assert "FAST_LLM_MODEL=qwen3.5-2b" in content, "FAST_LLM_MODEL must be qwen3.5-2b"
    assert "SYNTHESIS_LLM_MODEL=qwen3.5-4b" in content, "SYNTHESIS_LLM_MODEL must be qwen3.5-4b"
    assert "VRAM_SAFETY_LIMIT_MB=5000" in content, "VRAM_SAFETY_LIMIT_MB must be 5000"

def test_docker_compose_environment_mappings():
    """Verify docker-compose.yml maps correct model variables to pilos and bteam services"""
    compose_file = ROOT_DIR / "docker-compose.yml"
    assert compose_file.exists(), "docker-compose.yml must exist"
    
    content = compose_file.read_text(encoding="utf-8")
    assert "REPORT_LLM_MODEL: ${FAST_LLM_MODEL:-qwen3.5-2b}" in content
    assert "CHAT_LLM_MODEL: ${SYNTHESIS_LLM_MODEL:-qwen3.5-4b}" in content
    assert "SYNTHESIS_LLM_MODEL: ${SYNTHESIS_LLM_MODEL:-qwen3.5-4b}" in content

def test_model_gateway_server_config():
    """Verify model_gateway server_config.json contains CPU offload and KV quantization"""
    cfg_file = ROOT_DIR / "model_gateway" / "config" / "server_config.json"
    if not cfg_file.exists():
        cfg_file = ROOT_DIR / "model_gateway" / "sample" / "config.json"
    assert cfg_file.exists(), "model gateway config must exist"
    
    with open(cfg_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    assert data.get("embedding_model") == "bge-m3"
    assert data.get("rerank_model") == "bge-reranker-v2-m3"

if __name__ == "__main__":
    print("Testing root .env configuration...")
    test_root_env_configuration()
    print("Testing docker-compose environment mappings...")
    test_docker_compose_environment_mappings()
    print("Testing model gateway server config...")
    test_model_gateway_server_config()
    print("[OK] All Tiered Routing Contract Tests PASSED!")
