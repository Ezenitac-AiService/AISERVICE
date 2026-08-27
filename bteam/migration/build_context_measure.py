from __future__ import annotations

import argparse
import json
from pathlib import Path

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
}
EXCLUDED_SUFFIXES = {
    ".sql",
    ".dump",
    ".sqlite3",
    ".safetensors",
    ".pt",
    ".pth",
    ".bin",
    ".onnx",
    ".gguf",
    ".pyc",
}
EXCLUDED_NAMES = {"models", "chroma_db_oliview"}


def measure(root: Path) -> dict[str, object]:
    included_files = 0
    included_bytes = 0
    excluded_bytes = 0
    forbidden_included: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        excluded = path.suffix.lower() in EXCLUDED_SUFFIXES or any(
            part in EXCLUDED_DIRS or part in EXCLUDED_NAMES for part in path.parts
        )
        if excluded:
            excluded_bytes += path.stat().st_size
            continue
        included_files += 1
        included_bytes += path.stat().st_size
        if path.suffix.lower() in EXCLUDED_SUFFIXES or any(
            part in EXCLUDED_NAMES for part in path.parts
        ):
            forbidden_included.append(str(path.relative_to(root)))
    return {
        "root": str(root),
        "included_files": included_files,
        "included_bytes": included_bytes,
        "excluded_bytes": excluded_bytes,
        "forbidden_included": forbidden_included,
        "pass": not forbidden_included,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = measure(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if not result["pass"]:
        raise SystemExit(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
