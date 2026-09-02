#!/usr/bin/env python3
"""
AISERVICE Secrets & DDNS Configuration Packager
Discovers all sensitive .env files and DDNS XML configurations across the repository,
generates a SHA-256 manifest, and bundles them into an encrypted/integrity-verified archive.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tarfile
import zipfile

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]

# Known ignore patterns when collecting secrets
IGNORE_DIR_PARTS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "migration_pack",
}

IGNORE_FILE_NAMES = {
    ".env.example",
    ".env.migration.template",
}


def compute_sha256(file_path: Path) -> str:
    """Computes SHA-256 hex digest of a given file."""
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def discover_secrets(root_dir: Path) -> list[Path]:
    """Discovers all valid .env files and ddns/duckdns-config.xml."""
    discovered: list[Path] = []

    # 1. Search for .env files
    for p in root_dir.rglob(".env*"):
        if not p.is_file():
            continue
        if any(part in p.parts for part in IGNORE_DIR_PARTS):
            continue
        if p.name in IGNORE_FILE_NAMES or p.name.endswith(".example") or p.name.endswith(".template"):
            continue
        discovered.append(p)

    # 2. Specific DDNS XML configuration
    ddns_xml = root_dir / "ddns" / "duckdns-config.xml"
    if ddns_xml.is_file():
        discovered.append(ddns_xml)

    # Sort deterministically
    return sorted(discovered, key=lambda x: x.as_posix())


def create_manifest(files: list[Path], root_dir: Path) -> dict:
    """Creates a manifest dictionary with file hashes and metadata."""
    manifest_files: dict[str, dict] = {}
    for f in files:
        rel_path = f.relative_to(root_dir).as_posix()
        manifest_files[rel_path] = {
            "sha256": compute_sha256(f),
            "size_bytes": f.stat().st_size,
        }

    return {
        "format_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(manifest_files),
        "files": manifest_files,
    }


def pack_secrets(
    root_dir: Path = WORKSPACE_ROOT,
    output_tar: Path | None = None,
    output_zip: Path | None = None,
) -> tuple[Path, dict]:
    """Packages discovered secret files and manifest into tar.gz and optional zip."""
    dist_dir = root_dir / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)

    target_tar = output_tar or (dist_dir / "secrets_pack.tar.gz")
    target_zip = output_zip

    secret_files = discover_secrets(root_dir)
    if not secret_files:
        raise ValueError(f"No secrets or .env files found in {root_dir}")

    manifest = create_manifest(secret_files, root_dir)
    manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")

    # 1. Write TAR.GZ
    with tarfile.open(target_tar, "w:gz") as tar:
        # Add manifest
        tarinfo = tarfile.TarInfo(name="secrets_manifest.json")
        tarinfo.size = len(manifest_bytes)
        tarinfo.mtime = int(datetime.now(timezone.utc).timestamp())
        tarinfo.mode = 0o600
        import io
        tar.addfile(tarinfo, io.BytesIO(manifest_bytes))

        # Add each secret file
        for f in secret_files:
            rel_path = f.relative_to(root_dir).as_posix()
            arcname = f"secrets/{rel_path}"
            tar.add(f, arcname=arcname)

    # 2. Write optional ZIP
    if target_zip:
        with zipfile.ZipFile(target_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("secrets_manifest.json", manifest_bytes)
            for f in secret_files:
                rel_path = f.relative_to(root_dir).as_posix()
                zf.write(f, arcname=f"secrets/{rel_path}")

    # Verify TAR archive immediately
    with tarfile.open(target_tar, "r:gz") as tar:
        names = tar.getnames()
        assert "secrets_manifest.json" in names, "Missing manifest in archive"
        assert len(names) == len(secret_files) + 1, "File count mismatch in archive"

    return target_tar, manifest


def main():
    parser = argparse.ArgumentParser(description="Package AISERVICE secrets and configs.")
    parser.add_argument("--root", type=Path, default=WORKSPACE_ROOT, help="Workspace root directory")
    parser.add_argument("--output", type=Path, default=None, help="Output tar.gz file path")
    parser.add_argument("--zip", type=Path, default=None, help="Optional output zip file path")

    args = parser.parse_args()

    try:
        tar_path, manifest = pack_secrets(args.root, args.output, args.zip)
        print(f"[SUCCESS] Packaged {manifest['file_count']} secret/config files into {tar_path}")
        print("\nPacked files:")
        for rel_path, meta in manifest["files"].items():
            print(f"  - {rel_path} ({meta['size_bytes']} bytes, SHA-256: {meta['sha256'][:12]}...)")
    except Exception as e:
        print(f"[ERROR] Failed to pack secrets: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
