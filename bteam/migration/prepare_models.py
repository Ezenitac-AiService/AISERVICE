from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

EXCLUDED = {".git", ".venv", "venv", "__pycache__"}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_model_manifest(source: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file() or any(part in EXCLUDED for part in path.parts):
            continue
        records.append(
            {
                "path": str(path.relative_to(source)),
                "size": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    return records


def copy_verified(
    source: Path, destination: Path, manifest: list[dict[str, object]]
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for record in manifest:
        relative = Path(str(record["path"]))
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and file_sha256(target) == record["sha256"]:
            continue
        temporary = target.with_suffix(target.suffix + ".green.tmp")
        shutil.copy2(source / relative, temporary)
        if file_sha256(temporary) != record["sha256"]:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"checksum mismatch while copying {relative}")
        temporary.replace(target)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Checksum and optionally copy model weights without touching Blue"
    )
    parser.add_argument("--source", action="append", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--copy", action="store_true", help="perform non-destructive Green copy"
    )
    args = parser.parse_args()
    manifests = {str(source): build_model_manifest(source) for source in args.source}
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifests, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if args.copy:
        for source, manifest in manifests.items():
            copy_verified(Path(source), args.destination, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
