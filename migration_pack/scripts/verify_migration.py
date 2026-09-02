#!/usr/bin/env python3
"""마이그레이션 후 정확히 11개 endpoint와 하드웨어를 검증합니다."""

from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

SSL_CTX = ssl._create_unverified_context()

def build_endpoints(
    gateway_port: int | str = 80, secondary_gateway_port: int | str = 8080
) -> list[dict[str, Any]]:
    """현재 Compose gateway와 보조 포트에 맞춘 11개 검증 endpoint를 구성합니다."""
    gateway = f"http://127.0.0.1:{gateway_port}"
    secondary = f"http://127.0.0.1:{secondary_gateway_port}"
    return [
    {
        "id": "gateway_root",
        "name": "Nginx Gateway Root (80)",
        "url": f"{gateway}/",
        "method": "GET",
        "category": "HTTP",
        "expected_status": [200],
    },
    {
        "id": "gateway_secondary",
        "name": "Nginx Gateway Secondary (8080)",
        "url": f"{secondary}/",
        "method": "GET",
        "category": "HTTP",
        "expected_status": [200],
    },
    {
        "id": "model_gateway_health",
        "name": "Model Gateway (LLM)",
        "url": "http://127.0.0.1:8081/health",
        "method": "GET",
        "category": "AI",
        "expected_status": [200],
    },
    {
        "id": "bge_m3_embedding",
        "name": "BGE-M3 Embedding",
        "url": "http://127.0.0.1:8090/v1/models",
        "method": "GET",
        "category": "AI",
        "expected_status": [200],
    },
    {
        "id": "bge_reranker",
        "name": "BGE Reranker",
        "url": "http://127.0.0.1:8091/v1/models",
        "method": "GET",
        "category": "AI",
        "expected_status": [200],
    },
    {
        "id": "pilos_web",
        "name": "Pilos Web",
        "url": f"{gateway}/ateam/pilos/",
        "method": "GET",
        "category": "HTTP",
        "expected_status": [200],
    },
    {
        "id": "oliview_frontend",
        "name": "Oliview Frontend",
        "url": f"{gateway}/bteam/oliview/",
        "method": "GET",
        "category": "HTTP",
        "expected_status": [200],
    },
    {
        "id": "oliview_backend",
        "name": "Oliview Backend API",
        "url": f"{gateway}/bteam/oliview/api/health",
        "method": "GET",
        "category": "HTTP",
        "expected_status": [200],
    },
    {
        "id": "oliview_chatbot_a",
        "name": "Oliview Chatbot A (Streamlit)",
        "url": f"{gateway}/bteam/chata/",
        "method": "GET",
        "category": "HTTP",
        "expected_status": [200],
    },
    {
        "id": "oliview_chatbot_b",
        "name": "Oliview Chatbot B (FastAPI)",
        "url": f"{gateway}/bteam/chatb/",
        "method": "GET",
        "category": "HTTP",
        "expected_status": [200],
    },
    {
        "id": "redis",
        "name": "Redis Session Store (PING-PONG)",
        "url": "tcp://127.0.0.1:6379",
        "method": "PING",
        "category": "REDIS",
        "expected_status": [200],
    },
    ]


ENDPOINTS: list[dict[str, Any]] = build_endpoints()


def _tcp_probe(host: str, port: int, *, redis: bool = False) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=3) as conn:
            if redis:
                conn.sendall(b"*1\r\n$4\r\nPING\r\n")
                response = conn.recv(64)
                return response.startswith(b"+PONG"), response.decode(
                    "utf-8", errors="replace"
                ).strip()
            return True, "TCP port is listening and responsive."
    except OSError as exc:
        return False, str(exc)


def test_endpoint(ep: dict[str, Any], timeout: int = 15) -> dict[str, Any]:
    started = time.perf_counter()
    if ep.get("category") in {"DATABASE", "REDIS"}:
        parsed = ep["url"].split(":")
        passed, message = _tcp_probe(
            parsed[1].lstrip("/"), int(parsed[2]), redis=ep["category"] == "REDIS"
        )
        result = {
            "id": ep["id"],
            "name": ep["name"],
            "url": ep["url"],
            "status_code": 200 if passed else 0,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "status": "PASS" if passed else "FAIL",
            "passed": passed,
            "message": message,
        }
        if not passed:
            result["error"] = message
        return result

    request = urllib.request.Request(ep["url"], method=ep.get("method", "GET"))
    try:
        with urllib.request.urlopen(
            request, timeout=timeout, context=SSL_CTX
        ) as response:
            status_code = response.getcode()
            body = response.read(4096)
            passed = status_code in ep["expected_status"] and (
                status_code != 200 or bool(body) or ep.get("allow_empty_body", False)
            )
            message = (
                "HTTP response and payload accepted"
                if passed
                else "HTTP response payload was empty or status was unexpected"
            )
            result = {
                "id": ep["id"],
                "name": ep["name"],
                "url": ep["url"],
                "status_code": status_code,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "status": "PASS" if passed else "FAIL",
                "passed": passed,
                "message": message,
            }
            if not passed:
                result["error"] = message
            return result
    except urllib.error.HTTPError as exc:
        return {
            "id": ep["id"],
            "name": ep["name"],
            "url": ep["url"],
            "status_code": exc.code,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "status": "FAIL",
            "passed": False,
            "message": f"HTTP {exc.code}: {exc.reason}",
            "error": f"HTTP {exc.code}: {exc.reason}",
        }
    except (OSError, urllib.error.URLError) as exc:
        return {
            "id": ep["id"],
            "name": ep["name"],
            "url": ep["url"],
            "status_code": 0,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "status": "FAIL",
            "passed": False,
            "message": str(exc),
            "error": str(exc),
        }


def main():
    parser = argparse.ArgumentParser(description="AISERVICE Migration Verification Suite")
    parser.add_argument("--json-report", type=str, help="Path to save JSON verification report")
    parser.add_argument("--timeout", type=int, default=30, help="Per-endpoint timeout in seconds")
    args = parser.parse_args()


def _hardware_detected() -> dict[str, Any]:
    try:
        from model_gateway.scripts.probe_hardware import (
            probe_cpu_features,
            probe_gpu_features,
        )

        cpu = probe_cpu_features()
        gpu = probe_gpu_features()
        return {
            "cpu_model": cpu.get("model_name", "Unknown CPU"),
            "avx_supported": bool(cpu.get("avx", False)),
            "gpu_model": gpu.get("name", "None"),
            "vram_mb": int(gpu.get("vram_total_mb", 0)),
            "compute_capability": gpu.get("compute_capability", "none"),
        }
    except (OSError, ImportError, KeyError, TypeError, ValueError, RuntimeError) as exc:
        return {"error": str(exc)}

    total = len(results)
    pass_rate = (passed_count / total) * 100

    print("-" * 75)
    print(f" Summary: Total {total} Endpoints | Passed: {passed_count} | Failed: {failed_count} ({pass_rate:.1f}%)")
    print("=" * 75)

    report_data = {
        "timestamp": datetime.now().isoformat(),
        "total_endpoints": total,
        "passed_endpoints": passed,
        "failed_endpoints": failed,
        "duration_seconds": round(
            sum(float(result.get("latency_ms", 0)) for result in results) / 1000, 3
        ),
        "hardware_detected": hardware_detected or {},
        "data_integrity": integrity,
        "results": results,
    }

    if args.json_report:
        with open(args.json_report, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        print(f" Report saved to: {args.json_report}")

    sys.exit(0 if failed_count == 0 else 1)


if __name__ == "__main__":
    raise SystemExit(main())
