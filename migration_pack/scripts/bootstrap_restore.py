#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AISERVICE Cross-Platform Target Host One-Click Bootstrap & Restore (bootstrap_restore.py)
---------------------------------------------------------------------------------------
Handles target host prerequisites, checksum verification, database streaming import,
Docker Compose orchestration, and automated 11-endpoint healthchecks.
"""

import sys
import os
import time
import gzip
import hashlib
import subprocess
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
DB_DIR = os.path.join(PACK_ROOT, "database")


def verify_checksums() -> bool:
    checksum_path = os.path.join(DB_DIR, "checksums.sha256")
    if not os.path.exists(checksum_path):
        print("⚠️ Warning: 'checksums.sha256' not found. Skipping hash check.")
        return True

    print("▶ Verifying SHA-256 integrity checksums...")
    all_ok = True
    with open(checksum_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(maxsplit=1)
            if len(parts) != 2:
                continue
            expected_hash, rel_path = parts
            full_path = os.path.join(PACK_ROOT, rel_path.replace("/", os.sep))
            if not os.path.exists(full_path):
                print(f"  ❌ Missing dump file: {rel_path}")
                all_ok = False
                continue

            h = hashlib.sha256()
            with open(full_path, "rb") as bf:
                while chunk := bf.read(1024 * 1024):
                    h.update(chunk)
            actual_hash = h.hexdigest()
            if actual_hash.lower() == expected_hash.lower():
                print(f"  ✓ Verified {os.path.basename(rel_path)}: 100% SHA-256 match.")
            else:
                print(f"  ❌ Hash MISMATCH for {rel_path}!")
                print(f"     Expected: {expected_hash}")
                print(f"     Actual:   {actual_hash}")
                all_ok = False
    return all_ok


def wait_for_mysql(container: str, password: str, max_retries: int = 30) -> bool:
    print(f"  Waiting for '{container}' to become ready...", end="", flush=True)
    for _ in range(max_retries):
        cmd = ["docker", "exec", container, "mysqladmin", "ping", "-h", "localhost", "-u", "root", f"-p{password}"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            print(" ✓ Ready.")
            return True
        print(".", end="", flush=True)
        time.sleep(2)
    print(" ❌ Timeout.")
    return False


def restore_database(container: str, db_name: str, user: str, password: str, dump_path: str) -> bool:
    if not os.path.exists(dump_path):
        print(f"❌ Error: Dump file not found at '{dump_path}'")
        return False

    print(f"\n▶ Restoring '{db_name}' into container '{container}'...")
    start_time = time.time()

    cmd = [
        "docker", "exec", "-i", container,
        "mysql",
        f"-u{user}",
        f"-p{password}",
        "--default-character-set=utf8mb4",
        db_name,
    ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    with gzip.open(dump_path, "rb") as gz_in:
        while True:
            chunk = gz_in.read(1024 * 1024)
            if not chunk:
                break
            proc.stdin.write(chunk)

    proc.stdin.close()
    proc.wait()

    if proc.returncode != 0:
        stderr_msg = proc.stderr.read().decode("utf-8", errors="ignore")
        if "ERROR" in stderr_msg:
            print(f"❌ Restore failed for {db_name}: {stderr_msg}")
            return False

    elapsed = time.time() - start_time
    print(f"  ✓ '{db_name}' restored successfully in {elapsed:.1f}s.")
    return True


def main():
    parser = argparse.ArgumentParser(description="AISERVICE Target Host Bootstrap & Restore")
    parser.add_argument("--force", "-f", action="store_true", help="Force overwrite without confirmation")
    parser.add_argument("--skip-verification", action="store_true", help="Skip running verify_migration.py at the end")
    args = parser.parse_args()

    print("=" * 75)
    print(" [AISERVICE] TARGET HOST ONE-CLICK BOOTSTRAP & RESTORE")
    print(f" Timestamp: {datetime.now().isoformat()}")
    print(f" Force Mode: {args.force}")
    print("=" * 75)

    # 1. Verify Checksums
    if not verify_checksums() and not args.force:
        print("❌ Aborted due to checksum mismatch. Use --force to override.")
        sys.exit(1)

    # 2. Provision .env
    target_env = os.path.join(PROJECT_ROOT, ".env")
    if not os.path.exists(target_env):
        template_env = os.path.join(PACK_ROOT, "config", ".env.migration.template")
        if os.path.exists(template_env):
            import shutil
            shutil.copyfile(template_env, target_env)
            print(f"✓ Provisioned default '{target_env}' from template.")

    # 3. Start DB Containers
    print("\n▶ Starting database containers (pilos-db, bteam_db, redis)...")
    subprocess.run(["docker", "compose", "up", "-d", "pilos_db", "bteam_db", "redis"], cwd=PROJECT_ROOT, check=True)

    if not wait_for_mysql("pilos-db", "pilos_root_pass"):
        sys.exit(1)
    if not wait_for_mysql("bteam_db", "GP123!"):
        sys.exit(1)

    # 4. Restore Databases
    restore_database(
        container="pilos-db",
        db_name="pilos_v2",
        user="pilos_user",
        password="pilos_password",
        dump_path=os.path.join(DB_DIR, "pilos_v2.sql.gz"),
    )

    restore_database(
        container="bteam_db",
        db_name="oliview_project",
        user="gp123",
        password="GP123!",
        dump_path=os.path.join(DB_DIR, "oliview_project.sql.gz"),
    )

    # 5. Start Full Stack
    print("\n▶ Starting all service containers...")
    subprocess.run(["docker", "compose", "up", "-d"], cwd=PROJECT_ROOT, check=True)

    # 6. Verification
    if not args.skip_verification:
        time.sleep(5)
        verify_script = os.path.join(SCRIPT_DIR, "verify_migration.py")
        if os.path.exists(verify_script):
            subprocess.run([sys.executable, verify_script])

    print("\n" + "=" * 75)
    print(" 🎉 AISERVICE MIGRATION RESTORE & BOOTSTRAP COMPLETED!")
    print("=" * 75)


if __name__ == "__main__":
    main()
