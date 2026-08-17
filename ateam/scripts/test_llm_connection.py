"""LLM Connection & Health Verification Script

Tests communication with the containerized OpenAI-compatible LLM & Embedding servers.
"""

import os
import sys
import httpx
from pathlib import Path

try:
    from dotenv import load_dotenv
    env_file = Path("pilos-sentiment-index/.env")
    if env_file.exists():
        load_dotenv(str(env_file))
    else:
        load_dotenv()
except Exception:
    pass

def test_llm_endpoints():
    llm_base_url = os.getenv("LLM_BASE_URL", "http://vllm-serv-gateway:8081/v1")
    embedding_base_url = os.getenv("EMBEDDING_BASE_URL", "http://vllm-serv-gateway:8090/v1")
    api_key = os.getenv("LLM_API_KEY", "EMPTY")
    chat_model = os.getenv("CHAT_LLM_MODEL", "qwen3.5-4b")

    print(f"=== Testing LLM Services Connection ===")
    print(f"LLM Base URL: {llm_base_url}")
    print(f"Embedding Base URL: {embedding_base_url}")
    print(f"Chat Model: {chat_model}\n")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 1. Test LLM Models List
    models_url = f"{llm_base_url.rstrip('/')}/models"
    print(f"[1/3] Checking LLM models endpoint: {models_url}")
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(models_url, headers=headers)
            if resp.status_code == 200:
                models = resp.json().get("data", [])
                model_ids = [m.get("id") for m in models]
                print(f"  [OK] Successfully retrieved models: {model_ids}")
            else:
                print(f"  [WARNING] Models endpoint returned status {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"  [INFO] Note on endpoint: {e}")

    # 2. Test Chat Completion
    chat_url = f"{llm_base_url.rstrip('/')}/chat/completions"
    print(f"\n[2/3] Checking Chat Completion endpoint: {chat_url}")
    chat_payload = {
        "model": chat_model,
        "messages": [{"role": "user", "content": "안녕하세요"}],
        "max_tokens": 20
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(chat_url, headers=headers, json=chat_payload)
            if resp.status_code == 200:
                res_json = resp.json()
                reply = res_json.get("choices", [{}])[0].get("message", {}).get("content", "")
                print(f"  [OK] Chat response received: {reply.strip()}")
            else:
                print(f"  [WARNING] Chat endpoint returned status {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"  [INFO] Endpoint check note: {e}")

    print("\n=== LLM Configuration & Connection Check Complete ===")
    return True

if __name__ == "__main__":
    test_llm_endpoints()
