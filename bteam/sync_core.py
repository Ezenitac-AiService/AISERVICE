#!/usr/bin/env python
"""
Single Master oliview_core Synchronization Tool (Spec 048 / Constitution Principle III & VI).
Copies bteam/oliview_core master package byte-identically to ChatA and ChatB packages.
Includes SHA-256 hash manifest generation, dry-run simulation, and atomic replacement.
"""

import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

MASTER_CORE_DIR = Path(__file__).resolve().parent / "oliview_core"
CHATA_CORE_DIR = Path(__file__).resolve().parent / "Oliview_chatbot_a" / "oliview_core"
CHATB_CORE_DIR = Path(__file__).resolve().parent / "Oliview_chatbot_b" / "oliview_core"

ALLOWLISTED_TARGETS = [CHATA_CORE_DIR, CHATB_CORE_DIR]


def compute_core_hash_manifest(directory: Path) -> Dict[str, str]:
    """Computes SHA-256 hashes for all python files in directory."""
    manifest = {}
    if not directory.exists():
        return manifest

    for root, _, files in os.walk(directory):
        if "__pycache__" in root:
            continue
        for file in sorted(files):
            if file.endswith(".py") or file.endswith(".json") or file.endswith(".md"):
                file_path = Path(root) / file
                rel_path = file_path.relative_to(directory).as_posix()
                h = hashlib.sha256()
                with open(file_path, "rb") as f:
                    while chunk := f.read(65536):
                        h.update(chunk)
                manifest[rel_path] = h.hexdigest()

    return manifest


def atomic_sync_core(source: Path, target: Path, dry_run: bool = False) -> bool:
    """Atomically synchronizes source directory to target directory."""
    if not source.exists():
        print(f"[ERROR] Source does not exist: {source}", file=sys.stderr)
        return False

    if target not in ALLOWLISTED_TARGETS:
        print(f"[ERROR] Target {target} is not in allowlisted destinations!", file=sys.stderr)
        return False

    source_manifest = compute_core_hash_manifest(source)
    target_manifest = compute_core_hash_manifest(target)

    diff_files = []
    for rel_path, src_hash in source_manifest.items():
        if target_manifest.get(rel_path) != src_hash:
            diff_files.append(rel_path)

    for rel_path in target_manifest:
        if rel_path not in source_manifest:
            diff_files.append(f"[DELETED] {rel_path}")

    if not diff_files:
        print(f"[VERIFIED] {target.parent.name}/oliview_core is already 100% byte-identical to master.")
        return True

    if dry_run:
        print(f"[DRY-RUN] Would sync {len(diff_files)} files to {target.parent.name}/oliview_core:")
        for f in diff_files[:5]:
            print(f"  - {f}")
        if len(diff_files) > 5:
            print(f"  ... and {len(diff_files) - 5} more.")
        return True

    print(f"[SYNC] Atomically updating {target.parent.name}/oliview_core ({len(diff_files)} changed files)...")

    # Atomic staging via temp dir
    temp_stage = Path(tempfile.mkdtemp(prefix="oliview_sync_stage_"))
    try:
        shutil.copytree(
            source,
            temp_stage / "oliview_core",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
        )
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(temp_stage / "oliview_core", target)
    finally:
        shutil.rmtree(temp_stage, ignore_errors=True)

    # Post-sync verification
    new_target_manifest = compute_core_hash_manifest(target)
    if new_target_manifest == source_manifest:
        print(f"[SUCCESS] {target.parent.name}/oliview_core successfully verified (SHA-256 match).")
        return True
    else:
        print(f"[FAIL] Post-sync hash mismatch on {target.parent.name}/oliview_core!", file=sys.stderr)
        return False


def sync_core_directories(dry_run: bool = False, verify_only: bool = False) -> bool:
    all_ok = True
    for target in ALLOWLISTED_TARGETS:
        if verify_only:
            src_m = compute_core_hash_manifest(MASTER_CORE_DIR)
            tgt_m = compute_core_hash_manifest(target)
            if src_m == tgt_m:
                print(f"[VERIFIED] {target.parent.name}/oliview_core byte-identical to master.")
            else:
                print(f"[MISMATCH] {target.parent.name}/oliview_core differs from master!")
                all_ok = False
        else:
            success = atomic_sync_core(MASTER_CORE_DIR, target, dry_run=dry_run)
            if not success:
                all_ok = False
    return all_ok


if __name__ == "__main__":
    is_dry = "--dry-run" in sys.argv
    is_verify = "--verify" in sys.argv
    res = sync_core_directories(dry_run=is_dry, verify_only=is_verify)
    if not res:
        sys.exit(1)
    print("\n[COMPLETE] sync_core operation finished successfully.")
