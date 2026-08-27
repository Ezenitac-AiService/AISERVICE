from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_dry_run(
    *,
    mysql_dump: Path,
    chroma_db: Path,
    blue_endpoints: dict[str, str],
    green_endpoints: dict[str, str],
) -> dict[str, object]:
    collisions = sorted(
        key
        for key in green_endpoints
        if green_endpoints.get(key) == blue_endpoints.get(key)
    )
    if collisions:
        raise ValueError(
            f"Green validation endpoints collide with Blue: {', '.join(collisions)}"
        )
    return {
        "mode": "VALIDATION_DRY_RUN",
        "mysql_dump": {
            "path": str(mysql_dump),
            "bytes": mysql_dump.stat().st_size,
            "sha256": sha256(mysql_dump),
        },
        "chroma_snapshot": {
            "path": str(chroma_db),
            "bytes": chroma_db.stat().st_size,
            "sha256": sha256(chroma_db),
            "legacy_collection": "oliview_review_sentences",
            "write": False,
        },
        "redis": {
            "profile": "isolated-empty",
            "legacy_scan": False,
            "legacy_delete": False,
        },
        "endpoint_collisions": collisions,
        "blue_mutated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mysql-dump", type=Path, required=True)
    parser.add_argument("--chroma-db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_dry_run(
        mysql_dump=args.mysql_dump,
        chroma_db=args.chroma_db,
        blue_endpoints={},
        green_endpoints={
            "mysql": "green-snapshot",
            "chroma": "green-snapshot",
            "redis": "green-empty",
        },
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
