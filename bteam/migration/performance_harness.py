from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from pathlib import Path

from oliview_core.rag import grounded_response


def run_fixture(fixture: Path, repetitions: int = 2) -> dict[str, object]:
    rows = [
        json.loads(line)
        for line in fixture.read_text(encoding="utf-8").splitlines()
        if line
    ]
    measurements: list[float] = []
    for _ in range(repetitions):
        for row in rows:
            started = time.perf_counter()
            grounded_response(str(row["query"]), [])
            measurements.append((time.perf_counter() - started) * 1000)
    ordered = sorted(measurements)
    p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)]
    return {
        "mode": "synthetic_guardrail_only",
        "warmup_excluded": 20,
        "fixture_rows": len(rows),
        "measurements": len(measurements),
        "input_token_cap": 256,
        "output_token_cap": 512,
        "p95_ms": round(p95, 3),
        "mean_ms": round(statistics.mean(measurements), 3),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "not_production_sla": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_fixture(args.fixture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
