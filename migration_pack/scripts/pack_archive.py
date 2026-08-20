#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AISERVICE Single Archive Packager (pack_archive.py)
---------------------------------------------------
Packages the entire migration_pack directory into a standalone compressed
archive (.tar.gz or .zip) for single-file transfer.
"""

import sys
import os
import tarfile
import zipfile
import argparse
from datetime import datetime

# Windows Console UTF-8 safety
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PACK_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(PACK_ROOT, ".."))


def make_tar_gz(output_path: str):
    print(f"▶ Creating tar.gz archive: {output_path}...")
    with tarfile.open(output_path, "w:gz") as tar:
        tar.add(PACK_ROOT, arcname="migration_pack")
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"✓ Created '{output_path}' ({size_mb:.1f} MB)")


def make_zip(output_path: str):
    print(f"▶ Creating zip archive: {output_path}...")
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zip_out:
        for root, _, files in os.walk(PACK_ROOT):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, PROJECT_ROOT)
                zip_out.write(file_path, arcname=rel_path)
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"✓ Created '{output_path}' ({size_mb:.1f} MB)")


def main():
    today_str = datetime.now().strftime("%Y%m%d")
    default_archive_name = f"aiservice_migration_pack_{today_str}.tar.gz" if not sys.platform.startswith("win") else f"aiservice_migration_pack_{today_str}.zip"
    default_out = os.path.join(PROJECT_ROOT, default_archive_name)

    parser = argparse.ArgumentParser(description="AISERVICE Single Archive Packager")
    parser.add_argument("--output", type=str, default=default_out, help="Output archive path")
    parser.add_argument("--format", choices=["tar.gz", "zip"], default="zip" if sys.platform.startswith("win") else "tar.gz")
    args = parser.parse_args()

    print("=" * 70)
    print(" [AISERVICE] SINGLE ARCHIVE PACKAGER")
    print(f" Source Pack: {PACK_ROOT}")
    print(f" Output File: {args.output}")
    print("=" * 70)

    if args.format == "tar.gz" or args.output.endswith(".tar.gz") or args.output.endswith(".tgz"):
        make_tar_gz(args.output)
    else:
        make_zip(args.output)

    print("\n" + "=" * 70)
    print(" 🎉 PACKAGING COMPLETED!")
    print("=" * 70)


if __name__ == "__main__":
    main()
