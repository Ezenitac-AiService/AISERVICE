#!/usr/bin/env python3
"""환경 변수 기반 MySQL 안전 스트리밍 덤프 생성기."""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from migration_pack.scripts.env_utils import load_environment, required_environment

SCRIPT_DIR = Path(__file__).resolve().parent
PACK_ROOT = SCRIPT_DIR.parent
PROJECT_ROOT = PACK_ROOT.parent
DB_DIR = PACK_ROOT / "database"
DB_DIR.mkdir(parents=True, exist_ok=True)


class DatabaseExportError(RuntimeError):
    """DB export contract failure."""


def get_database_targets(
    environment: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    """현재 번들의 `.env`에서 두 MySQL 대상과 자격 증명을 구성합니다."""
    env = dict(environment or load_environment(PROJECT_ROOT))
    required = [
        "PILOS_DB_USER",
        "PILOS_DB_PASSWORD",
        "PILOS_DB_ROOT_PASSWORD",
        "PILOS_DB_NAME",
        "BTEAM_DB_USER",
        "BTEAM_DB_PASSWORD",
        "BTEAM_DB_ROOT_PASSWORD",
        "BTEAM_DB_NAME",
    ]
    missing = required_environment(env, required)
    if missing:
        raise DatabaseExportError("필수 DB 환경 변수 누락: " + ", ".join(missing))
    targets = [
        {
            "db_name": env["PILOS_DB_NAME"],
            "container": env.get("PILOS_DB_CONTAINER", "pilos-db"),
            "user": env["PILOS_DB_USER"],
            "password": env["PILOS_DB_PASSWORD"],
            "root_password": env["PILOS_DB_ROOT_PASSWORD"],
            "output_file": str(DB_DIR / f"{env['PILOS_DB_NAME']}.sql.gz"),
        },
        {
            "db_name": env["BTEAM_DB_NAME"],
            "container": env.get("BTEAM_DB_CONTAINER", "bteam_db"),
            "user": env["BTEAM_DB_USER"],
            "password": env["BTEAM_DB_PASSWORD"],
            "root_password": env["BTEAM_DB_ROOT_PASSWORD"],
            "output_file": str(DB_DIR / f"{env['BTEAM_DB_NAME']}.sql.gz"),
        },
    ]
    if "GREEN_DB_NAME" in env and check_container_running(env.get("GREEN_DB_CONTAINER", "mysql-green")):
        targets.append(
            {
                "db_name": env["GREEN_DB_NAME"],
                "container": env.get("GREEN_DB_CONTAINER", "mysql-green"),
                "user": env.get("GREEN_DB_USER", "bteam_green"),
                "password": env.get("GREEN_DB_PASSWORD", ""),
                "root_password": env.get(
                    "GREEN_DB_ROOT_PASSWORD", env.get("GREEN_DB_PASSWORD", "")
                ),
                "output_file": str(DB_DIR / f"{env['GREEN_DB_NAME']}.sql.gz"),
            }
        )
    return targets


def _docker_env(password: str) -> list[str]:
    # MYSQL_PWD를 사용해 비밀번호가 명령행 인자/일반 로그에 노출되지 않게 합니다.
    return ["-e", f"MYSQL_PWD={password}"]


def check_container_running(container_name: str) -> bool:
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return container_name in result.stdout.split()


def count_database_rows(target: Mapping[str, str]) -> tuple[int, str]:
    """information_schema의 엔진별 추정 행 수를 측정합니다.

    정확한 전체 COUNT(*)는 대형 DB에서 패키징 시간을 폭발시키므로, manifest에는
    측정 방식도 함께 기록합니다.
    """
    query = (
        "SELECT COALESCE(SUM(TABLE_ROWS),0) "
        "FROM information_schema.tables WHERE table_schema='"
        + target["db_name"].replace("'", "''")
        + "';"
    )
    command = [
        "docker",
        "exec",
        *_docker_env(target["root_password"]),
        target["container"],
        "mysql",
        "-uroot",
        "-s",
        "-N",
        "-e",
        query,
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=True, timeout=30
        )
        value = result.stdout.strip()
        return (
            (int(value), "information_schema.TABLE_ROWS")
            if value.isdigit()
            else (0, "unavailable")
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0, "unavailable"


def dump_database(target: Mapping[str, str]) -> dict[str, Any]:
    """MySQL dirty-page 정합성을 확보한 뒤 gzip 스트리밍 덤프를 생성합니다."""
    container = target["container"]
    if not check_container_running(container):
        raise DatabaseExportError(f"컨테이너가 실행 중이 아닙니다: {container}")

    db_name = target["db_name"]
    output_path = Path(target["output_file"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "docker",
        "exec",
        *_docker_env(target["password"]),
        container,
        "mysqldump",
        f"-u{target['user']}",
        "--single-transaction",
        "--quick",
        "--routines",
        "--triggers",
        "--events",
        "--hex-blob",
        "--default-character-set=utf8mb4",
        "--max_allowed_packet=512M",
        "--net_buffer_length=16384",
        db_name,
    ]

    row_count, row_source = count_database_rows(target)
    flush_cmd = [
        "docker",
        "exec",
        *_docker_env(target["root_password"]),
        container,
        "mysql",
        "-uroot",
        "-e",
        "FLUSH TABLES WITH READ LOCK;",
    ]
    flush = subprocess.run(
        flush_cmd, capture_output=True, text=True, timeout=30, check=False
    )
    if flush.returncode != 0:
        raise DatabaseExportError(f"MySQL 안전 flush 실패: {container}")

    start = time.time()
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdout is not None
    with gzip.open(output_path, "wb", compresslevel=9) as gz_out:
        while chunk := proc.stdout.read(1024 * 1024):
            gz_out.write(chunk)
    _, stderr = proc.communicate()
    if proc.returncode != 0:
        message = stderr.decode("utf-8", errors="replace")[-1000:]
        raise DatabaseExportError(
            f"mysqldump 실패({db_name}, code={proc.returncode}): {message}"
        )
    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
    print(
        f"  ✓ {db_name}: {output_path.name}, SHA-256 {digest[:12]}..., {time.time() - start:.1f}s"
    )
    return {
        "name": db_name,
        "dump_file": f"database/{output_path.name}",
        "size_bytes": output_path.stat().st_size,
        "sha256": digest,
        "row_count": row_count,
        "row_count_source": row_source,
    }


def main() -> int:
    try:
        environment = load_environment(PROJECT_ROOT)
        targets = get_database_targets(environment)
        metadata = [dump_database(target) for target in targets]
        (DB_DIR / "database_export_manifest.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        checksums = [f"{item['sha256']}  {item['dump_file']}" for item in metadata]
        (DB_DIR / "checksums.sha256").write_text(
            "\n".join(checksums) + "\n", encoding="utf-8"
        )
        print(f"완료: {len(metadata)}개 DB 덤프 생성")
        return 0
    except DatabaseExportError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
