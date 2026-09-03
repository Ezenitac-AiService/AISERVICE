#!/usr/bin/env python3
"""Ubuntu 타겟의 Docker volume/DB 복원 및 staged bootstrap 코어."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Mapping
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PACK_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(PACK_ROOT, ".."))
DB_DIR = os.path.join(PACK_ROOT, "database")


def verify_checksums() -> bool:
    checksum_file = PACK_ROOT / "checksums.sha256"
    if not checksum_file.is_file():
        checksum_file = DB_DIR / "checksums.sha256"
    if not checksum_file.is_file():
        log_warn("checksums.sha256가 없어 무결성 검증을 건너뜁니다.")
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


def get_restore_targets(
    project_root: Path | str = PROJECT_ROOT,
) -> list[dict[str, str]]:
    """복원 대상 DB 연결 정보를 root/ddns env에서 읽습니다."""
    env = load_environment(project_root)
    required = [
        "PILOS_DB_NAME",
        "PILOS_DB_USER",
        "PILOS_DB_PASSWORD",
        "PILOS_DB_ROOT_PASSWORD",
        "BTEAM_DB_NAME",
        "BTEAM_DB_USER",
        "BTEAM_DB_PASSWORD",
        "BTEAM_DB_ROOT_PASSWORD",
        "GREEN_DB_NAME",
        "GREEN_DB_USER",
        "GREEN_DB_PASSWORD",
        "GREEN_DB_ROOT_PASSWORD",
    ]
    missing = required_environment(env, required)
    if missing:
        raise RestoreError("필수 DB 환경 변수 누락: " + ", ".join(missing), 1)
    targets = [
        {
            "container": env.get("PILOS_DB_CONTAINER", "pilos-db"),
            "db_name": env["PILOS_DB_NAME"],
            "user": env["PILOS_DB_USER"],
            "password": env["PILOS_DB_PASSWORD"],
            "root_password": env["PILOS_DB_ROOT_PASSWORD"],
            "volume_name": "ateam_db_data",
            "dump_path": str(DB_DIR / f"{env['PILOS_DB_NAME']}.sql.gz"),
        },
        {
            "container": env.get("BTEAM_DB_CONTAINER", "bteam_db"),
            "db_name": env["BTEAM_DB_NAME"],
            "user": env["BTEAM_DB_USER"],
            "password": env["BTEAM_DB_PASSWORD"],
            "root_password": env["BTEAM_DB_ROOT_PASSWORD"],
            "volume_name": "bteam_bteam_mysql_data",
            "dump_path": str(DB_DIR / f"{env['BTEAM_DB_NAME']}.sql.gz"),
        },
    ]
    targets.append(
        {
            "container": env.get("GREEN_DB_CONTAINER", "mysql-green"),
            "db_name": env["GREEN_DB_NAME"],
            "user": env["GREEN_DB_USER"],
            "password": env["GREEN_DB_PASSWORD"],
            "root_password": env["GREEN_DB_ROOT_PASSWORD"],
            "volume_name": "green_mysql_data",
            "dump_path": str(DB_DIR / f"{env['GREEN_DB_NAME']}.sql.gz"),
        }
    )
    return targets


def _docker_password_args(password: str) -> list[str]:
    return ["-e", f"MYSQL_PWD={password}"]


def wait_for_mysql(container: str, password: str, max_retries: int = 60) -> bool:
    for _ in range(max_retries):
        result = subprocess.run(
            [
                "docker",
                "exec",
                *_docker_password_args(password),
                container,
                "mysqladmin",
                "ping",
                "-h",
                "localhost",
                "-uroot",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return True
        time.sleep(2)
    return False


def wait_for_redis(container: str = "aiservice-redis", max_retries: int = 60) -> bool:
    for _ in range(max_retries):
        result = subprocess.run(
            ["docker", "exec", container, "redis-cli", "ping"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and "PONG" in result.stdout.upper():
            return True
        time.sleep(2)
    return False


def wait_for_model_gateway(
    url: str = "http://vllm-serv-gateway:8081/health", max_retries: int = 60
) -> bool:
    for _ in range(max_retries):
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return True
        except (OSError, urllib.error.URLError):
            time.sleep(2)
    return False


def wait_for_http(url: str, max_retries: int = 60) -> bool:
    for _ in range(max_retries):
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return True
        except (OSError, urllib.error.URLError):
            time.sleep(2)
    return False


def check_mysql_has_data(
    container: str, user: str, password: str, db_name: str
) -> bool:
    query = (
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='"
        + db_name.replace("'", "''")
        + "';"
    )
    result = subprocess.run(
        [
            "docker",
            "exec",
            *_docker_password_args(password),
            container,
            "mysql",
            f"-u{user}",
            "-s",
            "-N",
            "-e",
            query,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return (
        result.returncode == 0
        and result.stdout.strip().isdigit()
        and int(result.stdout.strip()) > 0
    )


def restore_database_dump(
    container: str, db_name: str, user: str, password: str, dump_path: Path | str
) -> bool:
    path = Path(dump_path)
    if not path.is_file():
        log_warn(f"논리 덤프가 없어 복원을 건너뜁니다: {path.name}")
        return False
    command = [
        "docker",
        "exec",
        *_docker_password_args(password),
        "-i",
        container,
        "mysql",
        f"-u{user}",
        "--default-character-set=utf8mb4",
        db_name,
    ]
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        assert process.stdin is not None
        with gzip.open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                process.stdin.write(chunk)
        process.stdin.close()
        return_code = process.wait()
        stderr = (
            process.stderr.read().decode("utf-8", errors="replace")
            if process.stderr
            else ""
        )
        if return_code != 0:
            log_error(
                f"논리 DB 복원 실패({db_name}, code={return_code}): {stderr[-500:]}"
            )
            return False
        return True
    except (BrokenPipeError, OSError) as exc:
        log_error(f"논리 DB 스트리밍 실패({db_name}): {exc}")
        return False


def _compose_up(
    services: list[str], *, compose_file: Path | None = None, cwd: Path = PROJECT_ROOT
) -> None:
    command = ["docker", "compose"]
    if compose_file is not None:
        command.extend(["-f", str(compose_file)])
    command.extend(["up", "-d", *services])
    result = subprocess.run(command, cwd=cwd, check=False)
    if result.returncode != 0:
        raise RestoreError("Docker Compose 기동 실패", 2)


def restore_databases(
    targets: list[dict[str, str]],
    volume_results: Mapping[str, bool],
    *,
    force_dump: bool,
) -> None:
    for target in targets:
        physical_ok = bool(volume_results.get(target["volume_name"], False))
        has_data = check_mysql_has_data(
            target["container"], target["user"], target["password"], target["db_name"]
        )
        if physical_ok and has_data and not force_dump:
            log_info(
                f"{target['db_name']}: 검증된 물리 volume이 있어 SQL 중복 복원을 생략합니다."
            )
            continue
        if not restore_database_dump(
            target["container"],
            target["db_name"],
            target["user"],
            target["password"],
            target["dump_path"],
        ):
            raise RestoreError(f"논리 DB 복원 실패: {target['db_name']}", 3)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AISERVICE Ubuntu Restore Engine v2")
    parser.add_argument(
        "--yes", "-y", action="store_true", help="모든 overwrite/install 확인 자동 승인"
    )
    parser.add_argument(
        "--force", "-f", action="store_true", help="기존 volume/checksum override"
    )
    parser.add_argument("--dry-run", "-d", action="store_true", help="검사만 수행")
    parser.add_argument("--skip-gpu", action="store_true")
    parser.add_argument("--skip-ddns", action="store_true")
    parser.add_argument("--force-dump", action="store_true")
    parser.add_argument("--skip-verification", action="store_true")
    parser.add_argument(
        "--key-file",
        default=os.environ.get("MIGRATION_PACK_KEY_FILE"),
        help="외부 아카이브 복호화 키 파일",
    )
    parser.add_argument(
        "--archive",
        help="복호화·압축 해제할 .tar.gz.enc 또는 .zip.enc 경로",
    )
    parser.add_argument(
        "--extract-to",
        default=".",
        help="--archive의 압축 해제 대상 디렉터리",
    )
    return parser


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
    raise SystemExit(main())
