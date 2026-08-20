#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
 AISERVICE Master Migration Pack Builder Engine (make_migration_pack.py)
==============================================================================
A repeatable, automated tool that extracts fresh database dumps from live
containers, bundles the entire project codebase (clean of caches & node_modules),
generates SHA-256 manifests, and packages everything into a distributable,
one-click deployable Migration Archive (.zip / .tar.gz).
"""

import sys
import os
import time
import shutil
import zipfile
import tarfile
import hashlib
import json
import subprocess
import argparse
from datetime import datetime, timezone

# Windows Console UTF-8 safety
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MIGRATION_PACK_DIR = os.path.join(PROJECT_ROOT, "migration_pack")
DB_DIR = os.path.join(MIGRATION_PACK_DIR, "database")
SCRIPTS_DIR = os.path.join(MIGRATION_PACK_DIR, "scripts")
CONFIG_DIR = os.path.join(MIGRATION_PACK_DIR, "config")
DIST_DIR = os.path.join(PROJECT_ROOT, "dist")

# Exclusion patterns for clean codebase packaging
IGNORE_DIR_NAMES = {
    ".git",
    ".github",
    ".agents",
    ".specify",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    ".idea",
    ".vscode",
}

IGNORE_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".log",
    ".tmp",
    ".swp",
    ".DS_Store",
}


def log_step(title: str):
    print("\n" + "=" * 75)
    print(f" ▶ {title}")
    print("=" * 75)


def step_1_export_databases(skip_dump: bool = False):
    log_step("[1/4] Extracting Lossless Database Dumps from Live Containers")
    if skip_dump:
        print("  ⏩ Skipped database dump extraction as requested (--skip-dump).")
        return

    export_script = os.path.join(SCRIPTS_DIR, "export_databases.py")
    if not os.path.exists(export_script):
        print(f"❌ Error: Exporter script not found at {export_script}")
        sys.exit(1)

    cmd = [sys.executable, export_script]
    res = subprocess.run(cmd, check=True)
    if res.returncode != 0:
        print("❌ Database export failed.")
        sys.exit(1)


def step_2_build_dist_bundle(bundle_dir: str):
    log_step("[2/4] Assembling Clean Project Source Code & Migration Assets")
    if os.path.exists(bundle_dir):
        shutil.rmtree(bundle_dir)
    os.makedirs(bundle_dir, exist_ok=True)

    included_count = 0
    total_bytes = 0

    # Folders to copy
    CORE_FOLDERS = ["ateam", "bteam", "model_gateway", "gateway", "config", "ddns", "tests", "migration_pack"]
    CORE_FILES = ["docker-compose.yml", "run_all_services.bat", "run_all_services.sh", "README.md", "LICENSE"]

    for item in CORE_FILES:
        src = os.path.join(PROJECT_ROOT, item)
        if os.path.exists(src):
            dest = os.path.join(bundle_dir, item)
            shutil.copy2(src, dest)
            sz = os.path.getsize(src)
            total_bytes += sz
            included_count += 1
            print(f"  ✓ Bundled file: {item}")

    for folder in CORE_FOLDERS:
        src_folder = os.path.join(PROJECT_ROOT, folder)
        if not os.path.exists(src_folder):
            continue

        print(f"  📁 Bundling directory: {folder}/ ...")
        for root, dirs, files in os.walk(src_folder):
            # Prune ignored directories in-place
            dirs[:] = [d for d in dirs if d not in IGNORE_DIR_NAMES and not d.startswith(".")]

            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in IGNORE_EXTENSIONS or file in IGNORE_EXTENSIONS:
                    continue

                src_file = os.path.join(root, file)
                rel_path = os.path.relpath(src_file, PROJECT_ROOT)
                dest_file = os.path.join(bundle_dir, rel_path)

                os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                shutil.copy2(src_file, dest_file)
                sz = os.path.getsize(src_file)
                total_bytes += sz
                included_count += 1

    # Copy top-level bootstrap scripts into bundle root for instant execution
    shutil.copy2(os.path.join(SCRIPTS_DIR, "bootstrap_restore.bat"), os.path.join(bundle_dir, "bootstrap_restore.bat"))
    shutil.copy2(os.path.join(SCRIPTS_DIR, "bootstrap_restore.sh"), os.path.join(bundle_dir, "bootstrap_restore.sh"))
    shutil.copy2(os.path.join(CONFIG_DIR, ".env.migration.template"), os.path.join(bundle_dir, ".env.template"))

    print(f"\n✓ Assembly Complete: {included_count:,} files ({total_bytes / (1024*1024):.1f} MB) in '{bundle_dir}'")


def step_3_generate_manifest(bundle_dir: str) -> dict:
    log_step("[3/4] Generating Package Manifest & Checksums")
    checksum_map = {}
    manifest_path = os.path.join(bundle_dir, "migration_manifest.json")

    db_pilos = os.path.join(bundle_dir, "migration_pack", "database", "pilos_v2.sql.gz")
    db_bteam = os.path.join(bundle_dir, "migration_pack", "database", "oliview_project.sql.gz")

    def file_sha256(path: str) -> str:
        if not os.path.exists(path):
            return "N/A"
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                h.update(chunk)
        return h.hexdigest()

    pilos_hash = file_sha256(db_pilos)
    bteam_hash = file_sha256(db_bteam)

    manifest = {
        "manifest_version": "1.0.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "package_name": "AISERVICE-Cross-Platform-Migration-Pack",
        "databases": {
            "pilos_v2": {
                "dump_file": "migration_pack/database/pilos_v2.sql.gz",
                "size_mb": round(os.path.getsize(db_pilos) / (1024*1024), 2) if os.path.exists(db_pilos) else 0,
                "sha256": pilos_hash,
            },
            "oliview_project": {
                "dump_file": "migration_pack/database/oliview_project.sql.gz",
                "size_mb": round(os.path.getsize(db_bteam) / (1024*1024), 2) if os.path.exists(db_bteam) else 0,
                "sha256": bteam_hash,
            },
        },
    }

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Generated: {manifest_path}")

    # Checksums file
    cs_file = os.path.join(bundle_dir, "migration_pack", "database", "checksums.sha256")
    with open(cs_file, "w", encoding="utf-8") as f:
        f.write(f"{pilos_hash}  database/pilos_v2.sql.gz\n")
        f.write(f"{bteam_hash}  database/oliview_project.sql.gz\n")
    print(f"  ✓ Updated: {cs_file}")

    return manifest


def step_4_create_archive(bundle_dir: str, fmt: str) -> str:
    log_step("[4/4] Creating Compressed Migration Archive")
    os.makedirs(DIST_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"AISERVICE_Migration_Pack_{timestamp}"

    if fmt == "tar.gz":
        archive_path = os.path.join(DIST_DIR, f"{base_name}.tar.gz")
        print(f"▶ Compressing into '{archive_path}'...")
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(bundle_dir, arcname="AISERVICE")
    else:
        archive_path = os.path.join(DIST_DIR, f"{base_name}.zip")
        print(f"▶ Compressing into '{archive_path}'...")
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zip_out:
            for root, _, files in os.walk(bundle_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, bundle_dir)
                    zip_out.write(file_path, arcname=os.path.join("AISERVICE", rel_path))

    size_mb = os.path.getsize(archive_path) / (1024 * 1024)
    print(f"\n🎉 Archive Generated Successfully: {archive_path} ({size_mb:.1f} MB)")
    return archive_path


def main():
    parser = argparse.ArgumentParser(description="AISERVICE Master Migration Pack Builder Engine")
    parser.add_argument("--skip-dump", action="store_true", help="Skip extracting fresh database dumps (use existing .sql.gz)")
    parser.add_argument("--format", choices=["zip", "tar.gz"], default="zip" if sys.platform.startswith("win") else "tar.gz", help="Archive format")
    parser.add_argument("--no-archive", action="store_true", help="Keep unpacked folder in dist/ without compressing into a single archive")
    args = parser.parse_args()

    print("=" * 75)
    print(" 🚀 AISERVICE REPEATABLE MIGRATION PACK BUILDER")
    print(f" Source Root: {PROJECT_ROOT}")
    print(f" Archive Format: {args.format}")
    print("=" * 75)

    start_total = time.time()

    # Step 1: Export DBs
    step_1_export_databases(skip_dump=args.skip_dump)

    # Step 2: Assemble Code & Pack
    bundle_dir = os.path.join(DIST_DIR, "AISERVICE_Migration_Pack")
    step_2_build_dist_bundle(bundle_dir)

    # Step 3: Manifest & Checksums
    step_3_generate_manifest(bundle_dir)

    # Step 4: Create Archive
    if not args.no_archive:
        archive_file = step_4_create_archive(bundle_dir, args.format)
    else:
        archive_file = bundle_dir

    elapsed_total = time.time() - start_total
    print("\n" + "=" * 75)
    print(" 🎉 MIGRATION PACK BUILD COMPLETED IN {:.1f}s".format(elapsed_total))
    print(f" Output Location: {archive_file}")
    print("=" * 75)


if __name__ == "__main__":
    main()
