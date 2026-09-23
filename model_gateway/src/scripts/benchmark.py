"""
Automated Performance & Latency Benchmark Script for Feature 007 (Native llama-server)

Measures:
- TTFT (Time To First Token) in milliseconds
- TPS (Tokens Per Second) sustained generation speed
- Generates 100+ tokens via streaming chat completions

SC-003 Acceptance Criteria:
- 9B (qwen3.5-9b): TPS >= 42.0, TTFT <= 150.0ms
- 4B (qwen3.5-4b): TPS >= 60.0, TTFT <= 100.0ms

Exit Codes:
- 0: Passed all SC-003 thresholds
- 1: Failed threshold or runtime error
"""

import argparse
import json
import sys
import time
import httpx


TARGET_THRESHOLDS = {
    "9b": {"min_tps": 42.0, "max_ttft_ms": 150.0, "full_model": "qwen3.5-9b"},
    "qwen3.5-9b": {"min_tps": 42.0, "max_ttft_ms": 150.0, "full_model": "qwen3.5-9b"},
    "4b": {"min_tps": 60.0, "max_ttft_ms": 100.0, "full_model": "qwen3.5-4b"},
    "qwen3.5-4b": {"min_tps": 60.0, "max_ttft_ms": 100.0, "full_model": "qwen3.5-4b"},
}

MODEL_PROMPTS = {
    "4b": "123 + 456의 결과를 계산하기 위한 도구를 선택해.",
    "qwen3.5-4b": "123 + 456의 결과를 계산하기 위한 도구를 선택해.",
    "9b": "양자역학의 기본 개념을 상세하게 설명하고 주요 원리를 3가지 기술해줘.",
    "qwen3.5-9b": "양자역학의 기본 개념을 상세하게 설명하고 주요 원리를 3가지 기술해줘.",
}


def run_benchmark(model_key: str, gateway_url: str = "http://127.0.0.1:8081", max_tokens: int = 128) -> int:
    key = model_key.lower()
    if key not in TARGET_THRESHOLDS:
        print(f"❌ Unknown model '{model_key}'. Allowed: 9b, 4b, qwen3.5-9b, qwen3.5-4b", file=sys.stderr)
        return 1

    targets = TARGET_THRESHOLDS[key]
    model_name = targets["full_model"]
    min_tps = targets["min_tps"]
    max_ttft_ms = targets["max_ttft_ms"]
    prompt = MODEL_PROMPTS.get(key, "Please provide a detailed technical analysis.")

    print("=" * 70)
    print(f"🚀 Benchmarking Model Gateway Native C++ Engine: {model_name}")
    print(f"🎯 Target Thresholds: TPS >= {min_tps:.1f} tps, TTFT <= {max_ttft_ms:.1f} ms")
    print(f"🔗 Gateway URL: {gateway_url}/v1/chat/completions")
    print("=" * 70)

    endpoint = f"{gateway_url.rstrip('/')}/v1/chat/completions"
    payload = {
        "model": model_name,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "stream": True,
    }

    engine_timings = None
    try:
        with httpx.Client(timeout=60.0) as client:
            # Warm-up request to establish HTTP connection and preheat KV cache
            try:
                client.post(
                    endpoint,
                    json={"model": model_name, "messages": [{"role": "user", "content": "warmup"}], "max_tokens": 1},
                    headers={"Content-Type": "application/json"}
                )
            except Exception:
                pass

            t_start = time.perf_counter()
            t_first_token = None
            token_count = 0
            full_text = []

            with client.stream("POST", endpoint, json=payload, headers={"Content-Type": "application/json"}) as response:
                if response.status_code != 200:
                    err_body = response.read().decode("utf-8", errors="replace")
                    print(f"❌ HTTP Error {response.status_code}: {err_body}", file=sys.stderr)
                    return 1

                for line in response.iter_lines():
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            if "timings" in chunk and isinstance(chunk["timings"], dict):
                                engine_timings = chunk["timings"]
                            choices = chunk.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content") or delta.get("reasoning_content") or ""
                                if content:
                                    if t_first_token is None:
                                        t_first_token = time.perf_counter()
                                    token_count += 1
                                    full_text.append(content)
                        except json.JSONDecodeError:
                            continue

    except Exception as exc:
        print(f"❌ Connection or Streaming Error: {exc}", file=sys.stderr)
        return 1

    t_end = time.perf_counter()

    if t_first_token is None or token_count == 0:
        print("❌ No tokens generated! Benchmark failed.", file=sys.stderr)
        return 1

    client_ttft_ms = (t_first_token - t_start) * 1000.0
    total_time_s = t_end - t_start
    gen_time_s = t_end - t_first_token

    # Prefer native C++ engine measurements if returned in SSE timings chunk
    if engine_timings and "prompt_ms" in engine_timings and "predicted_per_second" in engine_timings:
        ttft_ms = float(engine_timings["prompt_ms"])
        sustained_tps = float(engine_timings["predicted_per_second"])
        source_label = "Native C++ Engine Timings"
    else:
        ttft_ms = client_ttft_ms
        sustained_tps = (token_count - 1) / gen_time_s if (token_count > 1 and gen_time_s > 0) else (token_count / total_time_s)
        source_label = "Client-Side Measurements"

    e2e_tps = token_count / total_time_s if total_time_s > 0 else 0.0

    print("\n" + "─" * 70)
    print(f"📊 Benchmark Results for {model_name} ({source_label}):")
    print(f"   • Total Generated Tokens: {token_count} (Requirement: >= 100)")
    print(f"   • TTFT (Time to First Token): {ttft_ms:.2f} ms (Target: <= {max_ttft_ms:.1f} ms) [Client Wall: {client_ttft_ms:.2f} ms]")
    print(f"   • Sustained Generation TPS:   {sustained_tps:.2f} tokens/sec (Target: >= {min_tps:.1f})")
    print(f"   • End-to-End TPS:             {e2e_tps:.2f} tokens/sec")
    print(f"   • Total Wall Time:            {total_time_s:.2f} s")
    print("─" * 70)

    is_tokens_ok = token_count >= 100
    is_ttft_ok = ttft_ms <= max_ttft_ms
    is_tps_ok = sustained_tps >= min_tps

    print(f"  [{'PASS' if is_tokens_ok else 'FAIL'}] Token Count >= 100: {token_count}")
    print(f"  [{'PASS' if is_ttft_ok else 'FAIL'}] TTFT <= {max_ttft_ms:.1f} ms: {ttft_ms:.2f} ms")
    print(f"  [{'PASS' if is_tps_ok else 'FAIL'}] Sustained TPS >= {min_tps:.1f}: {sustained_tps:.2f} tps")
    print("=" * 70)

    if is_tokens_ok and is_ttft_ok and is_tps_ok:
        print("🎉 SC-003 Benchmark SUCCESS: All performance thresholds met!\n")
        return 0
    else:
        print("⚠️ SC-003 Benchmark FAILED: One or more thresholds not met.\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Model Gateway SC-003 Performance Benchmark")
    parser.add_argument("--model", required=True, choices=["9b", "4b", "qwen3.5-9b", "qwen3.5-4b"], help="Model to benchmark")
    parser.add_argument("--gateway-url", default="http://127.0.0.1:8081", help="Gateway URL (default: http://127.0.0.1:8081)")
    parser.add_argument("--max-tokens", type=int, default=128, help="Max tokens to generate (default: 128)")
    args = parser.parse_args()

    exit_code = run_benchmark(model_key=args.model, gateway_url=args.gateway_url, max_tokens=args.max_tokens)
    sys.exit(exit_code)
