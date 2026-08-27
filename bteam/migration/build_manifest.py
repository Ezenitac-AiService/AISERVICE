"""Create a redacted, file-level SHA-256 manifest for migration evidence.

The command is read-only with respect to source roots. Only the requested output
manifest is written, and environment-file contents are never emitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
}
SECRET_NAME = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts):
            continue
        yield path


def redacted_env_metadata(path: Path, repo_root: Path) -> dict[str, object]:
    keys: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = SECRET_NAME.match(line)
        if match:
            keys.append(match.group(1))
    return {
        "path": path.relative_to(repo_root).as_posix(),
        "sha256": sha256_file(path),
        "keys": sorted(set(keys)),
        "values_recorded": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("checksum-manifest.json"),
    )
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    roots = [
        repo_root / "bteam" / "oliview_core",
        repo_root / "bteam" / "Oliview_Project",
        repo_root / "bteam" / "Oliview_aspect_sentence_split",
        repo_root / "bteam" / "Oliview_aspect_sentiment",
        repo_root / "bteam" / "Oliview_LLM",
        repo_root / "bteam" / "Oliview_chatbot_a",
        repo_root / "bteam" / "Oliview_chatbot_b",
    ]
    files: list[dict[str, object]] = []
    for root in roots:
        if not root.exists():
            continue
        for path in iter_files(root):
            files.append(
                {
                    "path": path.relative_to(repo_root).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    env_files = [
        p
        for p in (repo_root / "bteam").rglob(".env")
        if not any(part in EXCLUDED_DIRS for part in p.relative_to(repo_root).parts)
    ]
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "excluded_directory_names": sorted(EXCLUDED_DIRS),
        "source_roots": [
            p.relative_to(repo_root).as_posix() for p in roots if p.exists()
        ],
        "files": files,
        "secret_files": [
            redacted_env_metadata(p, repo_root) for p in sorted(env_files)
        ],
        "values_recorded": False,
    }
    output = args.output if args.output.is_absolute() else repo_root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": output.relative_to(repo_root).as_posix(),
                "file_count": len(files),
                "secret_values_recorded": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
