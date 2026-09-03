#!/usr/bin/env python3
"""Real context-window scaling benchmark.

Each measured context size is sent to the running gateway. The script never
uses synthetic latency or a mock completion path. Context recommendations use
the largest successful measured point and nearest-rank P99 uses ``ceil``.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from benchmark import nearest_rank_percentile


def _request(base_url: str, context_tokens: int, timeout: float) -> dict[str, Any]:
    prompt = "context scaling token " * max(1, context_tokens // 4)
    payload = {"model": "qwen3.5-4b", "messages": [{"role": "user", "content": prompt}], "max_tokens": 256, "stream": False}
    request = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            ttfb = time.perf_counter() - started
            response.read()
            e2e = time.perf_counter() - started
            return {"status_code": response.status, "ok": 200 <= response.status < 300, "ttfb_seconds": ttfb, "e2e_seconds": e2e}
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        return {"status_code": 0, "ok": False, "error_type": type(exc).__name__}


def run_context_scaling(
    *,
    base_url: str,
    start_tokens: int = 8192,
    end_tokens: int = 16384,
    step_tokens: int = 1024,
    samples_per_point: int = 3,
    warm_up: int = 1,
    timeout_seconds: float = 180,
    report_path: str | None = None,
) -> dict[str, Any]:
    if start_tokens <= 0 or end_tokens < start_tokens or step_tokens <= 0 or samples_per_point <= 0:
        raise ValueError("invalid context scaling range")
    for _ in range(warm_up):
        _request(base_url, start_tokens, timeout_seconds)
    points: list[dict[str, Any]] = []
    context = start_tokens
    while context <= end_tokens:
        results = [_request(base_url, context, timeout_seconds) for _ in range(samples_per_point)]
        e2e = [float(item["e2e_seconds"]) for item in results if item.get("e2e_seconds") is not None]
        points.append({
            "context_tokens": context,
            "request_count": samples_per_point,
            "successful_count": sum(1 for item in results if item.get("ok")),
            "e2e_p99_seconds": nearest_rank_percentile(e2e),
            "ttfb_p99_seconds": nearest_rank_percentile([float(item["ttfb_seconds"]) for item in results if item.get("ttfb_seconds") is not None]),
            "within_10s": len(e2e) == samples_per_point and all(value <= 10 for value in e2e),
        })
        context += step_tokens
    successful = [point for point in points if point["successful_count"] == point["request_count"]]
    report = {
        "sample_set_id": "context_scaling_v1_dev_rtx3060_qwen3.5-4b",
        "base_url": base_url,
        "warm_up_excluded": warm_up,
        "nearest_rank": "ceil(0.99*N)",
        "recommended_context_tokens": max((point["context_tokens"] for point in successful), default=None),
        "points": points,
        "raw_prompts_logged": False,
    }
    if report_path:
        destination = Path(report_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run real context scaling requests")
    parser.add_argument("--base-url", default="http://127.0.0.1:8081")
    parser.add_argument("--report")
    parser.add_argument("--start-tokens", type=int, default=8192)
    parser.add_argument("--end-tokens", type=int, default=16384)
    parser.add_argument("--step-tokens", type=int, default=1024)
    parser.add_argument("--samples-per-point", type=int, default=3)
    parser.add_argument("--warm-up", type=int, default=1)
    args = parser.parse_args()
    output = run_context_scaling(base_url=args.base_url, start_tokens=args.start_tokens, end_tokens=args.end_tokens, step_tokens=args.step_tokens, samples_per_point=args.samples_per_point, warm_up=args.warm_up, report_path=args.report)
    print(json.dumps({"recommended_context_tokens": output["recommended_context_tokens"], "points": len(output["points"])}, ensure_ascii=False))

