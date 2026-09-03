#!/usr/bin/env python3
"""Evidence-only DEMO benchmark for the Model Gateway.

The runner performs real HTTP requests against an already running gateway. It
does not synthesize latency, GPU, or request-completion evidence. Warm-up
requests are separate from the measured sample and reports contain no prompts.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = os.environ.get("MODEL_GATEWAY_URL", "http://127.0.0.1:8081")
DEFAULT_SAMPLE_SET_ID = "sample_set_v1_dev_rtx3060_qwen3.5-4b"


def nearest_rank_percentile(values: list[float], percentile: float = 0.99) -> float | None:
    """Return the nearest-rank percentile using rank ``ceil(p * N)``."""

    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def _json_request(base_url: str, path: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            ttfb = time.perf_counter() - started
            raw = response.read()
            e2e = time.perf_counter() - started
            parsed = json.loads(raw.decode("utf-8"))
            return {
                "ok": 200 <= response.status < 300,
                "status_code": response.status,
                "ttfb_seconds": ttfb,
                "e2e_seconds": e2e,
                "gpu_acceleration": response.headers.get("X-Acceleration", ""),
                "gpu_slot": response.headers.get("X-GPU-Slot", ""),
                "response": parsed if isinstance(parsed, dict) else {},
            }
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"ok": False, "status_code": 0, "ttfb_seconds": None, "e2e_seconds": None, "error_type": type(exc).__name__}


def _gpu_snapshot() -> dict[str, Any]:
    """Read NVML-compatible nvidia-smi evidence; absence is unverified."""

    if not shutil.which("nvidia-smi"):
        return {"available": False, "reason": "nvidia-smi_unavailable"}
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {"available": False, "reason": "nvidia-smi_failed"}
        name, used, total = [part.strip() for part in result.stdout.splitlines()[0].split(",")[:3]]
        return {"available": True, "device": name, "used_vram_mb": int(used), "total_vram_mb": int(total)}
    except (OSError, subprocess.SubprocessError, ValueError, IndexError) as exc:
        return {"available": False, "reason": type(exc).__name__}


def _sample(workload: str, result: dict[str, Any], *, gpu_verified: bool) -> dict[str, Any]:
    return {
        "workload": workload,
        "ok": bool(result.get("ok")),
        "status_code": int(result.get("status_code", 0)),
        "ttfb_seconds": result.get("ttfb_seconds"),
        "e2e_seconds": result.get("e2e_seconds"),
        "gpu_evidence": bool(gpu_verified and result.get("gpu_acceleration") == "CUDA"),
    }


def _workload_summary(samples: list[dict[str, Any]], request_count: int) -> dict[str, Any]:
    e2e = [float(sample["e2e_seconds"]) for sample in samples if sample.get("e2e_seconds") is not None]
    ttfb = [float(sample["ttfb_seconds"]) for sample in samples if sample.get("ttfb_seconds") is not None]
    evidence_count = sum(1 for sample in samples if sample.get("gpu_evidence"))
    return {
        "request_count": request_count,
        "completed_count": sum(1 for sample in samples if sample.get("ok")),
        "evidence_count": evidence_count,
        "coverage_percent": round(evidence_count / request_count * 100, 2) if request_count else 0,
        "ttfb_p99_seconds": nearest_rank_percentile(ttfb),
        "e2e_p99_seconds": nearest_rank_percentile(e2e),
        "all_within_10s": len(e2e) == request_count and all(value <= 10 for value in e2e),
    }


def collect_gpu_evidence(base_url: str, *, request_count: int) -> dict[str, Any]:
    snapshot = _gpu_snapshot()
    fingerprint = os.environ.get("LLAMA_RUNTIME_BUILD_FINGERPRINT", "")
    profile: dict[str, Any] = {}
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/v1/profile", timeout=5) as response:
            profile = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, ValueError):
        pass
    runtime_hardware = profile.get("hardware", {}) if isinstance(profile, dict) else {}
    runtime_ok = bool(snapshot.get("available")) and runtime_hardware.get("backend") in {"llama.cpp-cuda", "cuda"}
    samples = [
        {"workload": workload, "request_count": request_count, "evidence_count": 0, "coverage_percent": 0}
        for workload in ("chat_llm", "embedding", "rerank")
    ]
    return {
        "source": "nvml+llama_runtime",
        "device": snapshot.get("device", "unverified"),
        "build_fingerprint": fingerprint or "unverified",
        "sample_set_id": DEFAULT_SAMPLE_SET_ID,
        "samples": samples,
        "all_requests_verified": bool(runtime_ok and fingerprint),
        "runtime_profile_verified": runtime_ok,
        "vram_snapshot": snapshot,
    }


def run_benchmark(
    output_path: str | None = None,
    *,
    base_url: str = DEFAULT_BASE_URL,
    request_count: int = 20,
    warm_up: int = 1,
    timeout_seconds: float = 180,
) -> dict[str, Any]:
    if request_count != 20:
        raise ValueError("DEMO acceptance requires exactly 20 measured requests per workload")
    if warm_up < 0:
        raise ValueError("warm_up must be non-negative")

    for _ in range(warm_up):
        _json_request(base_url, "/v1/chat/completions", {"model": "qwen3.5-4b", "messages": [{"role": "user", "content": "warm-up"}], "max_tokens": 256}, timeout_seconds)

    gpu = collect_gpu_evidence(base_url, request_count=request_count)
    gpu_verified = bool(gpu["all_requests_verified"])
    workloads = {
        "chat_llm": ("/v1/chat/completions", {"model": "qwen3.5-4b", "messages": [{"role": "user", "content": "고정 DEMO 벤치마크 질문에 답하세요."}], "max_tokens": 256, "stream": False}),
        "embedding": ("/v1/embeddings", {"model": "bge-m3", "input": ["고정 DEMO 임베딩 문장"]}),
        "rerank": ("/v1/rerank", {"model": "bge-reranker-v2-m3", "query": "고정 DEMO 질의", "documents": ["고정 DEMO 문서"]}),
    }
    samples: dict[str, list[dict[str, Any]]] = {key: [] for key in workloads}
    for workload, (path, payload) in workloads.items():
        for _ in range(request_count):
            result = _json_request(base_url, path, payload, timeout_seconds)
            sample = _sample(workload, result, gpu_verified=gpu_verified)
            samples[workload].append(sample)
            if sample["gpu_evidence"]:
                next(item for item in gpu["samples"] if item["workload"] == workload)["evidence_count"] += 1
        evidence_record = next(item for item in gpu["samples"] if item["workload"] == workload)
        evidence_record["coverage_percent"] = round(evidence_record["evidence_count"] / request_count * 100, 2)

    summaries = {key: _workload_summary(value, request_count) for key, value in samples.items()}
    all_within_10s = summaries["chat_llm"]["all_within_10s"]
    all_verified = bool(gpu["all_requests_verified"] and all(item["coverage_percent"] == 100 for item in gpu["samples"]))
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sample_set_id": DEFAULT_SAMPLE_SET_ID,
        "mode": "DEMO",
        "base_url": base_url,
        "warm_up_excluded": warm_up,
        "request_parameters": {"model": "qwen3.5-4b", "concurrency": 1, "max_tokens": 256},
        "gpu_evidence": gpu,
        "workloads": summaries,
        "cold_start": {"measured": False, "reason": "warm benchmark excludes cold start"},
        "overall": {"all_gpu_requests_verified": all_verified, "chat_e2e_100_percent_under_10s": all_within_10s, "passed": all_verified and all_within_10s},
        "raw_prompts_logged": False,
        "samples_logged": False,
    }
    if output_path:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the real DEMO GPU benchmark")
    parser.add_argument("--report", "-r", default=str(Path(__file__).resolve().parent.parent / "data/reports/rtx3060-demo-benchmark.json"))
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--request-count", type=int, default=20)
    parser.add_argument("--warm-up", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=180)
    args = parser.parse_args()
    result = run_benchmark(args.report, base_url=args.base_url, request_count=args.request_count, warm_up=args.warm_up, timeout_seconds=args.timeout_seconds)
    print(json.dumps({"passed": result["overall"]["passed"], "report": args.report}, ensure_ascii=False))
    raise SystemExit(0 if result["overall"]["passed"] else 2)
