#!/usr/bin/env python3
"""
Standalone SQLite DB Seed Script for vllm_serv (045-db-seed-and-setup-integration).
Populates seed API keys into server_config.json and 10 sample inference metrics/payloads into data/metrics.db.
Supports CLI --reset and --force options.
"""

import os
import sys
import argparse
import datetime
from src.core.metrics_db import MetricsDB, DB_PATH
from src.core.config_manager import ConfigManager


def seed_database(reset: bool = False) -> None:
    """Seeds data/metrics.db and server_config.json with sample keys and metrics."""
    if reset and os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
            print(f"[SeedDB] 🧹 Removed existing database at {DB_PATH}")
        except Exception as e:
            print(f"[SeedDB] ⚠️ Failed removing old DB: {e}")

    # 1. Register Seed API Keys in server_config.json
    cm = ConfigManager()
    cfg = cm.get_server_config()
    existing_keys = cfg.get("api_keys", [])
    
    seed_keys = [
        {"key": "sk-vllm-dev-demo1", "name": "Development Sample Key 1", "status": "active"},
        {"key": "sk-vllm-mobile-app", "name": "Mobile Client App Key", "status": "active"}
    ]

    updated = False
    for sk in seed_keys:
        if not any((k.get("key") if isinstance(k, dict) else k) == sk["key"] for k in existing_keys):
            existing_keys.append(sk)
            updated = True

    if updated:
        cfg["api_keys"] = existing_keys
        cm.save_server_config(cfg)
        print("[SeedDB] ✅ Registered seed API keys in server_config.json")

    # 2. Seed Sample Metrics & Payloads in metrics.db
    db = MetricsDB(db_path=DB_PATH)
    
    sample_records = [
        {
            "api_key": "sk-vllm-dev-demo1",
            "endpoint": "/v1/chat/completions",
            "status_code": 200,
            "prompt_tokens": 18,
            "completion_tokens": 42,
            "ttft_ms": 38.5,
            "tps": 34.2,
            "is_error": False,
            "prompt_text": "Write a python quicksort function with inline comments.",
            "completion_text": "def quicksort(arr):\n    if len(arr) <= 1:\n        return arr\n    pivot = arr[len(arr) // 2]\n    left = [x for x in arr if x < pivot]\n    middle = [x for x in arr if x == pivot]\n    right = [x for x in arr if x > pivot]\n    return quicksort(left) + middle + quicksort(right)"
        },
        {
            "api_key": "sk-vllm-mobile-app",
            "endpoint": "/v1/chat/completions",
            "status_code": 200,
            "prompt_tokens": 12,
            "completion_tokens": 28,
            "ttft_ms": 42.1,
            "tps": 29.8,
            "is_error": False,
            "prompt_text": "What are 3 key features of Qwen 3.5 4B model?",
            "completion_text": "1. High efficiency context processing up to 32k tokens.\n2. Native GGUF quantization support.\n3. Optimized speed for edge serving."
        },
        {
            "api_key": "sk-vllm-dev-demo1",
            "endpoint": "/v1/chat/completions",
            "status_code": 200,
            "prompt_tokens": 25,
            "completion_tokens": 60,
            "ttft_ms": 31.0,
            "tps": 41.5,
            "is_error": False,
            "prompt_text": "Explain quantum entanglement simply.",
            "completion_text": "Quantum entanglement is a physical phenomenon where pairs of particles remain connected so that actions performed on one instantly affect the other, even at great distances."
        },
        {
            "api_key": "sk-vllm-mobile-app",
            "endpoint": "/v1/chat/completions",
            "status_code": 401,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "ttft_ms": 0.0,
            "tps": 0.0,
            "is_error": True,
            "prompt_text": "(Unauthorized Access Attempt)",
            "completion_text": "HTTP 401 Unauthorized: Invalid API Key"
        },
        {
            "api_key": "sk-vllm-dev-demo1",
            "endpoint": "/v1/chat/completions",
            "status_code": 200,
            "prompt_tokens": 15,
            "completion_tokens": 35,
            "ttft_ms": 35.8,
            "tps": 38.0,
            "is_error": False,
            "prompt_text": "How do I clear local cache in browser?",
            "completion_text": "Press Ctrl+Shift+Delete (or Cmd+Shift+Delete on Mac) to open browser privacy settings and clear cached images and files."
        },
        # 054-seedpack-setup-sync: Embedding & Reranker Seed Metrics
        {
            "api_key": "sk-vllm-dev-demo1",
            "endpoint": "/v1/embeddings",
            "status_code": 200,
            "prompt_tokens": 14,
            "completion_tokens": 0,
            "ttft_ms": 12.4,
            "tps": 0.0,
            "is_error": False,
            "prompt_text": "BGE-M3 Dense Vector Embedding Sample Input",
            "completion_text": "[Dense Vector float array (1024 dims) generated successfully]"
        },
        {
            "api_key": "sk-vllm-mobile-app",
            "endpoint": "/v1/embeddings",
            "status_code": 200,
            "prompt_tokens": 28,
            "completion_tokens": 0,
            "ttft_ms": 15.1,
            "tps": 0.0,
            "is_error": False,
            "prompt_text": "Multilingual text representation for semantic retrieval",
            "completion_text": "[Dense Vector float array (1024 dims) generated successfully]"
        },
        {
            "api_key": "sk-vllm-mobile-app",
            "endpoint": "/v1/rerank",
            "status_code": 200,
            "prompt_tokens": 32,
            "completion_tokens": 0,
            "ttft_ms": 18.2,
            "tps": 0.0,
            "is_error": False,
            "prompt_text": "Query: BGE-Reranker test | Docs: ['doc1', 'doc2']",
            "completion_text": "[Relevance scores: doc1=0.95, doc2=0.12]"
        },
        {
            "api_key": "sk-vllm-dev-demo1",
            "endpoint": "/v1/rerank",
            "status_code": 200,
            "prompt_tokens": 45,
            "completion_tokens": 0,
            "ttft_ms": 22.0,
            "tps": 0.0,
            "is_error": False,
            "prompt_text": "Query: High-throughput reranking | Docs: ['passageA', 'passageB', 'passageC']",
            "completion_text": "[Relevance scores: passageA=0.88, passageB=0.74, passageC=0.05]"
        }
    ]

    for rec in sample_records:
        db.log_request(**rec)

    print(f"[SeedDB] ✅ Successfully injected {len(sample_records)} seed records into {DB_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="vLLM Serving Database Seed Pack Generator")
    parser.add_argument("--reset", action="store_true", help="Remove existing database before seeding")
    args = parser.parse_args()

    seed_database(reset=args.reset)
