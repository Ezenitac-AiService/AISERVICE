#!/usr/bin/env python3
"""
AISERVICE Secrets & DDNS Configuration Restorer
Verifies SHA-256 manifest integrity and restores .env files and DDNS configurations
into their exact target directory locations with safe permissions.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import zipfile

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]


def compute_sha256_bytes(data: bytes) -> str:
    """Computes SHA-256 hex digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def compute_sha256(file_path: Path) -> str:
    """Computes SHA-256 hex digest of a file on disk."""
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def load_archive(archive_path: Path) -> tuple[dict, dict[str, bytes]]:
    """Loads manifest and files from tar.gz or zip archive."""
    if not archive_path.exists():
        raise FileNotFoundError(f"Secrets archive not found at {archive_path}")

    files_data: dict[str, bytes] = {}
    manifest: dict | None = None

    if archive_path.name.endswith(".tar.gz") or archive_path.name.endswith(".tgz"):
        with tarfile.open(archive_path, "r:gz") as tar:
            for member in tar.getmembers():
                if member.name == "secrets_manifest.json":
                    f = tar.extractfile(member)
                    if f:
                        manifest = json.loads(f.read().decode("utf-8"))
                elif member.name.startswith("secrets/"):
                    rel_name = member.name[len("secrets/"):]
                    f = tar.extractfile(member)
                    if f:
                        files_data[rel_name] = f.read()
    elif archive_path.name.endswith(".zip"):
        with zipfile.ZipFile(archive_path, "r") as zf:
            for name in zf.namelist():
                if name == "secrets_manifest.json":
                    manifest = json.loads(zf.read(name).decode("utf-8"))
                elif name.startswith("secrets/"):
                    rel_name = name[len("secrets/"):]
                    files_data[rel_name] = zf.read(name)
    else:
        raise ValueError(f"Unsupported archive format: {archive_path}. Use .tar.gz or .zip")

    if not manifest:
        raise ValueError("Archive is missing 'secrets_manifest.json'")

    return manifest, files_data


def restore_secrets(
    archive_path: Path,
    target_root: Path = WORKSPACE_ROOT,
    backup_existing: bool = True,
    dry_run: bool = False,
) -> list[str]:
    """Restores secrets from archive into target_root after full manifest verification."""
    manifest, files_data = load_archive(archive_path)

    manifest_files = manifest.get("files", {})
    if not manifest_files:
        raise ValueError("Manifest contains no file records")

    # Step 1: Verify all files in archive against manifest SHA-256 before writing
    restored_list: list[str] = []
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    for rel_path, meta in manifest_files.items():
        if rel_path not in files_data:
            raise ValueError(f"Manifest lists '{rel_path}' but file is missing in archive payload")

        content = files_data[rel_path]
        actual_sha = compute_sha256_bytes(content)
        expected_sha = meta.get("sha256")

        if actual_sha != expected_sha:
            raise ValueError(
                f"Integrity check failed for '{rel_path}': expected {expected_sha}, got {actual_sha}"
            )

    # Step 2: Perform restoration
    for rel_path, content in files_data.items():
        dest_file = target_root / rel_path

        if dry_run:
            restored_list.append(f"[DRY-RUN] Would write {rel_path} ({len(content)} bytes)")
            continue

        # Backup existing file if requested
        if dest_file.exists() and backup_existing:
            backup_path = dest_file.with_name(f"{dest_file.name}.bak.{timestamp}")
            shutil.copy2(dest_file, backup_path)

        # Create parent directories
        dest_file.parent.mkdir(parents=True, exist_ok=True)

        # Write file contents
        dest_file.write_bytes(content)

        # Set secure permissions (chmod 600) on POSIX systems
        if os.name == "posix":
            try:
                dest_file.chmod(0o600)
            except OSError:
                pass

        # Post-write verification
        written_sha = compute_sha256(dest_file)
        expected_sha = manifest_files[rel_path]["sha256"]
        if written_sha != expected_sha:
            raise IOError(f"Write verification failed for {dest_file}")

        restored_list.append(f"Restored {rel_path} ({len(content)} bytes)")

    return restored_list


def main():
    parser = argparse.ArgumentParser(description="Restore AISERVICE secrets and configs.")
    parser.add_argument(
        "--archive",
        type=Path,
        default=WORKSPACE_ROOT / "dist" / "secrets_pack.tar.gz",
        help="Path to secrets archive file",
    )
    parser.add_argument("--target", type=Path, default=WORKSPACE_ROOT, help="Target workspace root")
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create .bak backup of existing files before overwriting",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify archive and show files without writing to disk",
    )

    args = parser.parse_args()

    try:
        results = restore_secrets(
            archive_path=args.archive,
            target_root=args.target,
            backup_existing=not args.no_backup,
            dry_run=args.dry_run,
        )
        mode = "DRY-RUN" if args.dry_run else "SUCCESS"
        print(f"[{mode}] Processed {len(results)} secret files into {args.target}")
        for r in results:
            print(f"  - {r}")
    except Exception as e:
        print(f"[ERROR] Restoration failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
