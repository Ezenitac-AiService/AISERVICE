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


# pytest should not treat this public probe helper as a test when imported by
# contract test modules.
test_endpoint.__test__ = False


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
    results: list[dict[str, Any]],
    hardware_detected: dict[str, Any] | None = None,
    data_integrity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    passed = sum(
        1
        for result in results
        if result.get("status") == "PASS" or result.get("passed") is True
    )
    total = len(results)
    failed = total - passed
    integrity = data_integrity or {}
    integrity_ok = integrity.get("status", "PASS") == "PASS"
    status = "PASS" if failed == 0 and total == 11 and integrity_ok else "FAIL"
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
        "data_integrity": integrity,
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


def _load_database_export_manifest() -> list[dict[str, Any]]:
    path = Path(__file__).resolve().parent.parent / "database" / "database_export_manifest.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _measure_database_integrity() -> list[dict[str, Any]]:
    """원본 매니페스트의 측정 방식으로 복원 대상 DB를 다시 측정합니다."""
    source = {str(item.get("name")): item for item in _load_database_export_manifest()}
    if not source:
        return []
    try:
        from migration_pack.scripts.export_databases import (
            count_database_rows,
            get_database_targets,
        )

        targets = get_database_targets()
    except (OSError, RuntimeError, ValueError, KeyError):
        return [
            {"name": name, "status": "FAIL", "error": "DB 측정 대상 환경을 읽을 수 없습니다"}
            for name in sorted(source)
        ]

    measurements: list[dict[str, Any]] = []
    for target in targets:
        name = target["db_name"]
        original = source.get(name)
        if original is None:
            continue
        current, method = count_database_rows(target)
        expected = int(original.get("row_count", -1))
        passed = method != "unavailable" and expected >= 0 and current == expected
        item = {
            "name": name,
            "expected_row_count": expected,
            "actual_row_count": current,
            "measurement_method": method,
            "status": "PASS" if passed else "FAIL",
        }
        if not passed:
            item["error"] = "복원 후 DB 행 수가 원본 측정값과 다릅니다"
        measurements.append(item)
    return measurements


def _fetch_json(url: str) -> Any:
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=5, context=SSL_CTX) as response:
        if response.status != 200:
            raise ValueError(f"HTTP {response.status}")
        return json.loads(response.read(1024 * 1024).decode("utf-8"))


def _measure_chroma_integrity() -> dict[str, Any]:
    """Chroma v2 API에서 canonical collection의 vector 수를 측정합니다."""
    volume_entry: dict[str, Any] = {}
    try:
        manifest = json.loads(
            (Path(__file__).resolve().parent.parent / "migration_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        volume_entry = next(
            (
                item
                for item in manifest.get("volumes", [])
                if item.get("volume_name") == "green_chroma_data"
            ),
            {},
        )
    except (OSError, json.JSONDecodeError):
        pass
    expected = volume_entry.get("vector_count")
    if expected is None:
        return {
            "collection": "oliview_review_sentences_v2",
            "status": "FAIL",
            "measurement_method": "Chroma v2 collection count API",
            "error": "원본 Chroma vector_count가 매니페스트에 없습니다",
        }

    base = "http://127.0.0.1:18000"
    try:
        collection_id = None
        try:
            collections = _fetch_json(
                base + "/api/v2/tenants/default_tenant/databases/default_database/collections"
            )
            for collection in collections if isinstance(collections, list) else []:
                if collection.get("name") == "oliview_review_sentences_v2":
                    collection_id = collection.get("id")
                    break
        except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
            collections = _fetch_json(base + "/api/v1/collections")
            for collection in collections if isinstance(collections, list) else []:
                if collection.get("name") == "oliview_review_sentences_v2":
                    collection_id = collection.get("id")
                    break
        if not collection_id:
            raise ValueError("canonical Chroma collection이 없습니다")
        try:
            count = _fetch_json(
                base
                + "/api/v2/tenants/default_tenant/databases/default_database/collections/"
                + str(collection_id)
                + "/count"
            )
        except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
            count = _fetch_json(base + f"/api/v1/collections/{collection_id}/count")
        actual = int(count if isinstance(count, int) else count.get("count", -1))
        passed = actual == int(expected)
        item = {
            "collection": "oliview_review_sentences_v2",
            "expected_vector_count": int(expected),
            "actual_vector_count": actual,
            "measurement_method": "Chroma v2 collection count API",
            "status": "PASS" if passed else "FAIL",
        }
        if not passed:
            item["error"] = "복원 후 Chroma vector 수가 원본 측정값과 다릅니다"
        return item
    except (OSError, ValueError, TypeError, KeyError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {
            "collection": "oliview_review_sentences_v2",
            "expected_vector_count": int(expected),
            "measurement_method": "Chroma v2 collection count API",
            "status": "FAIL",
            "error": str(exc),
        }


def collect_data_integrity() -> dict[str, Any]:
    databases = _measure_database_integrity()
    chroma = _measure_chroma_integrity()
    checks = databases + [chroma]
    return {
        "status": "PASS" if checks and all(item.get("status") == "PASS" for item in checks) else "FAIL",
        "databases": databases,
        "chroma": chroma,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AISERVICE 11-endpoint migration verification"
    )
    parser.add_argument(
        "--json-report",
        default=str(Path(__file__).resolve().parent.parent / "verification_report.json"),
    )
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument(
        "--gateway-port",
        type=int,
        default=int(os.environ.get("MIGRATION_VERIFY_GATEWAY_PORT", "80")),
        help="gateway primary port used for root and application routes",
    )
    parser.add_argument(
        "--secondary-gateway-port",
        type=int,
        default=int(os.environ.get("MIGRATION_VERIFY_SECONDARY_GATEWAY_PORT", "8080")),
        help="gateway secondary port used for the secondary root check",
    )
    parser.add_argument(
        "--skip-data-integrity",
        action="store_true",
        help="대상 DB/Chroma 데이터 수 비교를 생략합니다",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    started = time.perf_counter()
    endpoints = build_endpoints(args.gateway_port, args.secondary_gateway_port)
    results = [test_endpoint(endpoint, timeout=args.timeout) for endpoint in endpoints]
    integrity = {} if args.skip_data_integrity else collect_data_integrity()
    report = build_verification_report(results, _hardware_detected(), integrity)
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
