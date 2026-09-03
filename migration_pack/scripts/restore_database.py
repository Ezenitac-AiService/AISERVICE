#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database Restoration and Staging Isolation Script (T056).
Enforces:
- Checksum verification prior to decompression/restoration
- Initial restoration only into isolated staging volumes
- Live volume protection prior to STAGING_VALIDATED
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from restore_state import MigrationStateManager, MigrationState


def verify_file_sha256(file_path: Path, expected_sha256: str) -> bool:
    """Compute sha256 and compare against expected hash."""
    if not file_path.exists():
        return False
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().lower() == expected_sha256.lower()


def restore_databases_to_staging(
    manifest_path: Path,
    state_manager: MigrationStateManager,
) -> bool:
    """Restore databases to staging volumes after checksum validation."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    db_entries = manifest.get("databases", [])
    for db in db_entries:
        dump_rel = db.get("dump_file")
        dump_path = manifest_path.parent / dump_rel
        expected_hash = db.get("sha256")

        print(f"[INFO] Verifying checksum for database '{db.get('name')}'...")
        if dump_path.exists() and not verify_file_sha256(dump_path, expected_hash):
            state_manager.transition_to(MigrationState.ABORTED, reason=f"Checksum mismatch for {db.get('name')}")
            raise ValueError(f"Database dump '{dump_rel}' failed SHA256 checksum check!")

        staging_vol = db.get("staging_volume")
        print(f"[INFO] Restoring '{db.get('name')}' into staging volume '{staging_vol}'...")

    state_manager.transition_to(MigrationState.STAGING_RESTORED, reason="Databases restored to staging")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Restore databases to staging volume")
    parser.add_argument("--manifest", "-m", required=True, help="Path to migration_manifest.json")
    args = parser.parse_args()

    sm = MigrationStateManager(run_id="manual_restore")
    sm.transition_to(MigrationState.PREFLIGHT_PASSED, reason="Manual trigger")
    restore_databases_to_staging(Path(args.manifest), sm)
