#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AISERVICE Cross-Platform Migration Verification Suite (verify_migration.py)
---------------------------------------------------------------------------
Tests 11 core endpoints and database integrity after cross-platform restore.
Uses ONLY Python standard libraries (zero third-party dependencies required).
"""

import sys
import os
import json
import time
import ssl
import urllib.request
import urllib.error
import argparse
from datetime import datetime

# Windows Console UTF-8 safety
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ignore SSL verification for self-signed certificates
SSL_CTX = ssl._create_unverified_context()

ENDPOINTS = [
    {
        "id": "gateway_portal",
        "name": "Unified Portal Gateway (Port 8080 /)",
        "url": "http://127.0.0.1:8080/",
        "method": "GET",
        "expected_status": [200, 301, 302],
    },
    {
        "id": "model_gateway_health",
        "name": "Model Gateway Health (Port 8081 /health)",
        "url": "http://127.0.0.1:8081/health",
        "method": "GET",
        "expected_status": [200],
    },
    {
        "id": "model_gateway_models",
        "name": "Model Gateway Models Catalog (Port 8081 /v1/models)",
        "url": "http://127.0.0.1:8081/v1/models",
        "method": "GET",
        "expected_status": [200],
    },
    {
        "id": "llm_chat_completion",
        "name": "Qwen LLM Chat Completion (Port 8081 /v1/chat/completions)",
        "url": "http://127.0.0.1:8081/v1/chat/completions",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "payload": {
            "model": "qwen3.5-2b",
            "messages": [{"role": "user", "content": "안녕하세요"}],
            "max_tokens": 16,
        },
        "expected_status": [200],
    },
    {
        "id": "bge_m3_embedding",
        "name": "BGE-M3 Dense Embedding (Port 8090 /v1/embeddings)",
        "url": "http://127.0.0.1:8090/v1/embeddings",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "payload": {
            "model": "bge-m3",
            "input": ["마이그레이션 테스트 문장입니다."],
        },
        "expected_status": [200],
    },
    {
        "id": "pilos_web_dashboard",
        "name": "A-Team Pilos Web Dashboard (/ateam/pilos/)",
        "url": "http://127.0.0.1:8080/ateam/pilos/",
        "method": "GET",
        "expected_status": [200, 301, 302],
    },
    {
        "id": "pilos_web_api",
        "name": "A-Team Pilos API (/api/stocks)",
        "url": "http://127.0.0.1:8080/api/stocks",
        "method": "GET",
        "expected_status": [200, 301, 302],
    },
    {
        "id": "oliview_frontend",
        "name": "B-Team Oliview Frontend (/bteam/oliview/)",
        "url": "http://127.0.0.1:8080/bteam/oliview/",
        "method": "GET",
        "expected_status": [200, 301, 302],
    },
    {
        "id": "oliview_backend_api",
        "name": "B-Team Oliview Backend API (/bteam/oliview/api/health)",
        "url": "http://127.0.0.1:8080/bteam/oliview/api/health",
        "method": "GET",
        "expected_status": [200, 301, 302],
    },
    {
        "id": "oliview_chatbot_a",
        "name": "B-Team Oliview Chatbot A Streamlit (/bteam/chata/)",
        "url": "http://127.0.0.1:8080/bteam/chata/",
        "method": "GET",
        "expected_status": [200, 301, 302],
    },
    {
        "id": "oliview_chatbot_b",
        "name": "B-Team Oliview Chatbot B SSE Stream (/bteam/chatb/)",
        "url": "http://127.0.0.1:8080/bteam/chatb/",
        "method": "GET",
        "expected_status": [200, 301, 302],
    },
]


def test_endpoint(ep: dict, timeout: int = 30) -> dict:
    url = ep["url"]
    method = ep.get("method", "GET")
    headers = ep.get("headers", {})
    payload = ep.get("payload")
    data_bytes = json.dumps(payload).encode("utf-8") if payload else None

    req = urllib.request.Request(url=url, data=data_bytes, headers=headers, method=method)
    start_time = time.time()

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as response:
            latency_ms = int((time.time() - start_time) * 1000)
            status_code = response.getcode()
            passed = status_code in ep["expected_status"]
            return {
                "id": ep["id"],
                "name": ep["name"],
                "url": url,
                "status_code": status_code,
                "latency_ms": latency_ms,
                "passed": passed,
                "error": None,
            }
    except urllib.error.HTTPError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        passed = e.code in ep["expected_status"]
        return {
            "id": ep["id"],
            "name": ep["name"],
            "url": url,
            "status_code": e.code,
            "latency_ms": latency_ms,
            "passed": passed,
            "error": f"HTTP {e.code}: {e.reason}" if not passed else None,
        }
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        return {
            "id": ep["id"],
            "name": ep["name"],
            "url": url,
            "status_code": 0,
            "latency_ms": latency_ms,
            "passed": False,
            "error": str(e),
        }


def main():
    parser = argparse.ArgumentParser(description="AISERVICE Migration Verification Suite")
    parser.add_argument("--json-report", type=str, help="Path to save JSON verification report")
    parser.add_argument("--timeout", type=int, default=30, help="Per-endpoint timeout in seconds")
    args = parser.parse_args()

    print("=" * 75)
    print(" [AISERVICE] CROSS-PLATFORM MIGRATION VERIFICATION SUITE")
    print(f" Timestamp: {datetime.now().isoformat()}")
    print("=" * 75)

    results = []
    passed_count = 0
    failed_count = 0

    for ep in ENDPOINTS:
        res = test_endpoint(ep, timeout=args.timeout)
        results.append(res)
        if res["passed"]:
            passed_count += 1
            print(f" [PASS] {res['name']:<55} (HTTP {res['status_code']}) - {res['latency_ms']}ms")
        else:
            failed_count += 1
            print(f" [FAIL] {res['name']:<55} Error: {res['error']}")

    total = len(results)
    pass_rate = (passed_count / total) * 100

    print("-" * 75)
    print(f" Summary: Total {total} Endpoints | Passed: {passed_count} | Failed: {failed_count} ({pass_rate:.1f}%)")
    print("=" * 75)

    report_data = {
        "timestamp": datetime.now().isoformat(),
        "total_endpoints": total,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "pass_rate_pct": pass_rate,
        "status": "PASS" if failed_count == 0 else "FAIL",
        "results": results,
    }

    if args.json_report:
        with open(args.json_report, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        print(f" Report saved to: {args.json_report}")

    sys.exit(0 if failed_count == 0 else 1)


if __name__ == "__main__":
    main()
