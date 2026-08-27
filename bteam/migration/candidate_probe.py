from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def probe(url: str) -> dict[str, object]:
    started = time.perf_counter()
    try:
        with urlopen(url, timeout=3) as response:
            return {
                "url": url,
                "status": response.status,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }
    except (OSError, URLError) as error:
        return {
            "url": url,
            "status": None,
            "error": str(error),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = [probe(url) for url in args.url]
    artifact = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "route": "candidate-direct-probe",
        "blue_mutated": False,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0 if all(result.get("status") == 200 for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
