#!/usr/bin/env python3
"""마이그레이션 후 정확히 11개 endpoint와 하드웨어를 검증합니다."""

from __future__ import annotations

import argparse
import json
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

ENDPOINTS: list[dict[str, Any]] = [
    {
        "id": "gateway_root",
        "name": "Nginx Gateway Root (80)",
        "url": "http://127.0.0.1/",
        "method": "GET",
        "category": "HTTP",
        "expected_status": [200, 301, 302],
    },
    {
        "id": "gateway_secondary",
        "name": "Nginx Gateway Secondary (8080)",
        "url": "http://127.0.0.1:8080/",
        "method": "GET",
        "category": "HTTP",
        "expected_status": [200, 301, 302],
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
        "url": "http://127.0.0.1:8090/health",
        "method": "GET",
        "category": "AI",
        "expected_status": [200],
    },
    {
        "id": "bge_reranker",
        "name": "BGE Reranker",
        "url": "http://127.0.0.1:8091/health",
        "method": "GET",
        "category": "AI",
        "expected_status": [200],
    },
    {
        "id": "pilos_web",
        "name": "Pilos Web",
        "url": "http://127.0.0.1/ateam/pilos/",
        "method": "GET",
        "category": "HTTP",
        "expected_status": [200, 301, 302],
    },
    {
        "id": "oliview_frontend",
        "name": "Oliview Frontend",
        "url": "http://127.0.0.1/bteam/oliview/",
        "method": "GET",
        "category": "HTTP",
        "expected_status": [200, 301, 302],
    },
    {
        "id": "oliview_backend",
        "name": "Oliview Backend API",
        "url": "http://127.0.0.1/bteam/oliview/api/health",
        "method": "GET",
        "category": "HTTP",
        "expected_status": [200],
    },
    {
        "id": "oliview_chatbot_a",
        "name": "Oliview Chatbot A (Streamlit)",
        "url": "http://127.0.0.1/bteam/chata/",
        "method": "GET",
        "category": "HTTP",
        "expected_status": [200, 301, 302],
    },
    {
        "id": "oliview_chatbot_b",
        "name": "Oliview Chatbot B (FastAPI)",
        "url": "http://127.0.0.1/bteam/chatb/",
        "method": "GET",
        "category": "HTTP",
        "expected_status": [200, 301, 302],
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
        return {
            "id": ep["id"],
            "name": ep["name"],
            "url": ep["url"],
            "status_code": 200 if passed else 0,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "status": "PASS" if passed else "FAIL",
            "passed": passed,
            "message": message,
            "error": None if passed else message,
        }

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
            return {
                "id": ep["id"],
                "name": ep["name"],
                "url": ep["url"],
                "status_code": status_code,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "status": "PASS" if passed else "FAIL",
                "passed": passed,
                "message": message,
                "error": None if passed else message,
            }
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


def build_verification_report(
    results: list[dict[str, Any]], hardware_detected: dict[str, Any] | None = None
) -> dict[str, Any]:
    passed = sum(
        1
        for result in results
        if result.get("status") == "PASS" or result.get("passed") is True
    )
    total = len(results)
    failed = total - passed
    status = "PASS" if failed == 0 and total == 11 else "FAIL"
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "total_endpoints": total,
        "passed_endpoints": passed,
        "failed_endpoints": failed,
        "duration_seconds": round(
            sum(float(result.get("latency_ms", 0)) for result in results) / 1000, 3
        ),
        "hardware_detected": hardware_detected or {},
        "results": results,
        # 이전 소비자와의 하위 호환 필드
        "report_version": "2.0.0",
        "total_checks": total,
        "passed_checks": passed,
        "failed_checks": failed,
        "pass_rate_pct": round((passed / max(total, 1)) * 100, 1),
        "overall_status": "HEALTHY" if status == "PASS" else "DEGRADED",
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AISERVICE 11-endpoint migration verification"
    )
    parser.add_argument("--json-report", default="verification_report.json")
    parser.add_argument("--timeout", type=int, default=15)
    args = parser.parse_args(argv)
    started = time.perf_counter()
    results = [test_endpoint(endpoint, timeout=args.timeout) for endpoint in ENDPOINTS]
    report = build_verification_report(results, _hardware_detected())
    report["duration_seconds"] = round(time.perf_counter() - started, 3)
    if args.json_report:
        target = Path(args.json_report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
