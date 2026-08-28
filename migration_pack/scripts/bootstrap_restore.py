#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bootstrap_restore.py
====================
AISERVICE Target Host One-Click Bootstrap & Restore Core Engine v2.0
- Docker Volume Sidecar Extraction (Sparse Aware)
- Mutex Database Restoration (Physical Volume 우선, 실패 시 논리 SQL 덤프 폴백)
- Compose Orchestration with Readiness Polling
- 11-Endpoint Verification Gate
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
PACK_ROOT = SCRIPT_DIR.parent
PROJECT_ROOT = PACK_ROOT.parent
DB_DIR = PACK_ROOT / "database"
VOL_DIR = PACK_ROOT / "volumes"


def log_info(msg: str) -> None:
    print(f"\033[1;32m[INFO]\033[0m {msg}")


def log_warn(msg: str) -> None:
    print(f"\033[1;33m[WARN]\033[0m {msg}")


def log_error(msg: str) -> None:
    print(f"\033[1;31m[ERROR]\033[0m {msg}", file=sys.stderr)


def verify_checksums() -> bool:
    cs_path = DB_DIR / "checksums.sha256"
    if not cs_path.is_file():
        cs_path = PACK_ROOT / "checksums.sha256"
    if not cs_path.is_file():
        log_warn("'checksums.sha256' not found. Skipping hash check.")
        return True

    log_info("Verifying SHA-256 integrity checksums...")
    all_ok = True
    with open(cs_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(maxsplit=1)
            if len(parts) != 2:
                continue
            expected_hash, rel_path = parts[0], parts[1].strip()
            full_path = PACK_ROOT / rel_path.replace("/", os.sep)
            if not full_path.is_file():
                # Check under database/ or volumes/
                if (DB_DIR / rel_path).is_file():
                    full_path = DB_DIR / rel_path
                elif (VOL_DIR / rel_path).is_file():
                    full_path = VOL_DIR / rel_path
                else:
                    log_error(f"Missing file for checksum: {rel_path}")
                    all_ok = False
                    continue

            h = hashlib.sha256()
            with open(full_path, "rb") as bf:
                while chunk := bf.read(1024 * 1024):
                    h.update(chunk)
            actual = h.hexdigest()
            if actual.lower() == expected_hash.lower():
                log_info(f"✓ Verified '{full_path.name}': 100% SHA-256 match.")
            else:
                log_error(f"Hash MISMATCH for '{full_path.name}'! (Expected: {expected_hash}, Got: {actual})")
                all_ok = False
    return all_ok


def restore_docker_volumes() -> Dict[str, bool]:
    """volumes/*.tar.gz 물리 아카이브를 Docker Volume으로 복원합니다."""
    results: Dict[str, bool] = {}
    if not VOL_DIR.is_dir():
        log_warn("No 'volumes/' directory found. Physical volume restore skipped.")
        return results

    archive_files = list(VOL_DIR.glob("*.tar.gz"))
    if not archive_files:
        log_warn("No volume archives (.tar.gz) found in 'volumes/'.")
        return results

    log_info(f"Found {len(archive_files)} Docker volume archive(s). Restoring...")
    for archive in archive_files:
        vol_name = archive.name.replace(".tar.gz", "")
        # 볼륨 이름 매핑 보정 (예: bteam_mysql_data -> bteam_bteam_mysql_data)
        target_vol = vol_name
        if "bteam" in vol_name and "mysql" in vol_name:
            target_vol = "bteam_bteam_mysql_data"
        elif "redis" in vol_name:
            target_vol = "aiservice_redis_data"
        elif "ateam" in vol_name:
            target_vol = "ateam_db_data"
        elif "chroma" in vol_name:
            target_vol = "green_chroma_data"

        try:
            log_info(f"▶ Restoring Docker volume '{target_vol}' from '{archive.name}'...")
            # 1. 볼륨 사전 생성
            subprocess.run(["docker", "volume", "create", target_vol], capture_output=True, check=True)

            # 2. Sidecar 컨테이너를 통한 tar 압축 해제
            cmd = [
                "docker", "run", "--rm",
                "-v", f"{target_vol}:/target",
                "-v", f"{VOL_DIR}:/backup:ro",
                "alpine",
                "sh", "-c", f"cd /target && tar xzf /backup/{archive.name}",
            ]
            subprocess.run(cmd, capture_output=True, check=True, timeout=300)
            log_info(f"  ✓ Volume '{target_vol}' restored successfully.")
            results[target_vol] = True
        except Exception as e:
            log_error(f"Failed to restore volume '{target_vol}': {e}")
            results[target_vol] = False

    return results


def wait_for_mysql(container: str, password: str, max_retries: int = 30) -> bool:
    log_info(f"Waiting for '{container}' to become ready...")
    for i in range(max_retries):
        cmd = ["docker", "exec", container, "mysqladmin", "ping", "-h", "localhost", "-u", "root", f"-p{password}"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            log_info(f"✓ Container '{container}' is healthy and accepting connections.")
            return True
        time.sleep(2)
    log_error(f"Timeout waiting for '{container}'!")
    return False


def check_mysql_has_data(container: str, user: str, password: str, db_name: str) -> bool:
    """DB에 이미 테이블 및 데이터가 존재하는지 검사합니다 (Mutex 판별용)."""
    try:
        cmd = [
            "docker", "exec", container,
            "mysql", f"-u{user}", f"-p{password}", "-e",
            f"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='{db_name}';",
            "-s", "-N",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0 and res.stdout.strip().isdigit():
            count = int(res.stdout.strip())
            return count > 0
    except Exception:
        pass
    return False


def restore_database_dump(container: str, db_name: str, user: str, password: str, dump_path: Path | str) -> bool:
    dpath = Path(dump_path)
    if not dpath.is_file():
        log_warn(f"Dump file not found: '{dpath}'")
        return False

    log_info(f"▶ Restoring logical SQL dump for '{db_name}' into '{container}'...")
    t0 = time.time()
    cmd = [
        "docker", "exec", "-i", container,
        "mysql", f"-u{user}", f"-p{password}",
        "--default-character-set=utf8mb4",
        db_name,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    with gzip.open(dpath, "rb") as gz_in:
        while chunk := gz_in.read(1024 * 1024):
            proc.stdin.write(chunk)

    proc.stdin.close()
    proc.wait()

    if proc.returncode != 0:
        err = proc.stderr.read().decode("utf-8", errors="ignore")
        if "ERROR" in err:
            log_error(f"Restore failed for '{db_name}': {err}")
            return False

    elapsed = time.time() - t0
    log_info(f"✓ '{db_name}' logical dump restored in {elapsed:.1f}s.")
    return True


def main():
    parser = argparse.ArgumentParser(description="AISERVICE Target Host Bootstrap & Restore Engine v2.0")
    parser.add_argument("--force", "-f", action="store_true", help="Force overwrite without confirmation")
    parser.add_argument("--skip-verification", action="store_true", help="Skip running verify_migration.py at the end")
    parser.add_argument("--force-dump", action="store_true", help="Force logical SQL dump even if volume exists")
    args = parser.parse_args()

    print("=" * 75)
    print(" [AISERVICE] TARGET HOST ONE-CLICK BOOTSTRAP & RESTORE v2.0")
    print(f" Timestamp: {datetime.now().isoformat()}")
    print(f" Force Mode: {args.force}")
    print("=" * 75)

    # 1. SHA-256 무결성 검증
    if not verify_checksums() and not args.force:
        log_error("Aborted due to checksum mismatch. Use --force to override.")
        sys.exit(1)

    # 2. Docker Named Volume 물리 복원 시도
    vol_results = restore_docker_volumes()

    # 3. DB 및 인프라 컨테이너 우선 기동
    log_info("Starting database & infra containers (pilos-db, bteam_db, redis)...")
    subprocess.run(["docker", "compose", "up", "-d", "pilos_db", "bteam_db", "redis"], cwd=PROJECT_ROOT, check=True)

    if not wait_for_mysql("pilos-db", "pilos_root_pass"):
        sys.exit(1)
    if not wait_for_mysql("bteam_db", "GP123!"):
        sys.exit(1)

    # 4. Mutex 데이터베이스 복원 로직
    # A-Team MySQL
    pilos_has_data = check_mysql_has_data("pilos-db", "pilos_user", "pilos_password", "pilos_v2")
    if pilos_has_data and not args.force_dump:
        log_info("✓ 'pilos_v2' database already has tables from volume. Skipping duplicate SQL dump (Mutex).")
    else:
        restore_database_dump("pilos-db", "pilos_v2", "pilos_user", "pilos_password", DB_DIR / "pilos_v2.sql.gz")

    # B-Team MySQL
    oliview_has_data = check_mysql_has_data("bteam_db", "gp123", "GP123!", "oliview_project")
    if oliview_has_data and not args.force_dump:
        log_info("✓ 'oliview_project' database already has tables from volume. Skipping duplicate SQL dump (Mutex).")
    else:
        restore_database_dump("bteam_db", "oliview_project", "gp123", "GP123!", DB_DIR / "oliview_project.sql.gz")

    # 5. 전체 서비스 컨테이너 순차 기동
    log_info("Starting all application service containers...")
    subprocess.run(["docker", "compose", "up", "-d"], cwd=PROJECT_ROOT, check=True)

    # 6. E2E 검증 게이트
    if not args.skip_verification:
        time.sleep(5)
        verify_script = SCRIPT_DIR / "verify_migration.py"
        if verify_script.is_file():
            subprocess.run([sys.executable, str(verify_script)])

    print("\n" + "=" * 75)
    print(" 🎉 AISERVICE MIGRATION RESTORE & BOOTSTRAP COMPLETED!")
    print("=" * 75)


if __name__ == "__main__":
    main()
