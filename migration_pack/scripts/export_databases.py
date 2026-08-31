#!/usr/bin/env python3
"""환경 변수 기반 MySQL 안전 스트리밍 덤프 생성기."""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import sys
import shlex
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
    """현재 번들의 `.env`에서 기본 및 Green MySQL 대상을 구성합니다."""
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
        "GREEN_DB_USER",
        "GREEN_DB_PASSWORD",
        "GREEN_DB_ROOT_PASSWORD",
        "GREEN_DB_NAME",
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
    targets.append(
        {
            "db_name": env["GREEN_DB_NAME"],
            "container": env.get("GREEN_DB_CONTAINER", "mysql-green"),
            "user": env["GREEN_DB_USER"],
            "password": env["GREEN_DB_PASSWORD"],
            "root_password": env["GREEN_DB_ROOT_PASSWORD"],
            "output_file": str(DB_DIR / f"{env['GREEN_DB_NAME']}.sql.gz"),
        }
    )
    return targets


def _docker_env(password: str) -> list[str]:
    # MYSQL_PWD를 사용해 비밀번호가 명령행 인자/일반 로그에 노출되지 않게 합니다.
    return ["-e", f"MYSQL_PWD={password}"]


def resolve_running_container(name_or_service: str) -> str | None:
    """정확한 이름, Compose 라벨 및 이름 패턴 기반으로 실행 중인 DB 컨테이너를 탐색합니다."""
    if not name_or_service:
        return None
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Labels}}"],
            capture_output=True,
            text=True,
            check=True,
        )
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.strip().split("\t", 1)
            c_name = parts[0].strip()
            c_labels = parts[1].strip() if len(parts) > 1 else ""

            if c_name == name_or_service:
                return c_name
            if f"com.docker.compose.service={name_or_service}" in c_labels:
                return c_name
            clean_target = name_or_service.replace("-", "").replace("_", "")
            clean_cname = c_name.replace("-", "").replace("_", "")
            if clean_target in clean_cname:
                return c_name
    except (OSError, subprocess.CalledProcessError):
        pass
    return None


def check_container_running(container_name: str) -> bool:
    return resolve_running_container(container_name) is not None


def inspect_view_definers(target: Mapping[str, str], container: str) -> list[dict[str, str]]:
    """information_schema.VIEWS에서 invalid definer를 사전 탐지합니다."""
    query = (
        "SELECT TABLE_NAME, DEFINER, IS_UPDATABLE "
        "FROM information_schema.views WHERE TABLE_SCHEMA='"
        + target["db_name"].replace("'", "''")
        + "';"
    )
    command = [
        "docker",
        "exec",
        *_docker_env(target["root_password"]),
        container,
        "mysql",
        "-uroot",
        "-s",
        "-N",
        "-e",
        query,
    ]
    views = []
    try:
        res = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                parts = line.strip().split("\t")
                if parts and parts[0]:
                    views.append({
                        "table_name": parts[0],
                        "definer": parts[1] if len(parts) > 1 else "",
                        "is_updatable": parts[2] if len(parts) > 2 else "NO",
                    })
    except (OSError, subprocess.SubprocessError):
        pass
    return views


def find_invalid_view_definers(
    target: Mapping[str, str], container: str, views: list[dict[str, str]] | None = None
) -> list[dict[str, str]]:
    """View DEFINER가 실제 MySQL 계정으로 존재하는지 확인하고 invalid 항목을 반환합니다."""
    view_rows = views if views is not None else inspect_view_definers(target, container)
    if not view_rows:
        return []
    account_query = (
        "SELECT CONCAT(User, '@', Host) FROM mysql.user "
        "WHERE User IS NOT NULL ORDER BY User, Host;"
    )
    command = [
        "docker",
        "exec",
        *_docker_env(target["root_password"]),
        container,
        "mysql",
        "-uroot",
        "-s",
        "-N",
        "-e",
        account_query,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise DatabaseExportError(f"MySQL View DEFINER 검증 실패: {exc}") from exc
    if result.returncode != 0:
        raise DatabaseExportError(
            f"MySQL 계정 목록 조회 실패({target['db_name']}): {result.stderr[-500:]}"
        )
    accounts = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    invalid: list[dict[str, str]] = []
    for view in view_rows:
        definer = str(view.get("definer", ""))
        user, separator, host = definer.partition("@")
        candidates = {definer}
        if separator:
            candidates.add(f"{user}@%")
        if not any(candidate in accounts for candidate in candidates):
            invalid.append(view)
    return invalid


def check_database_connection(target: Mapping[str, str]) -> bool:
    """컨테이너 내부 mysqladmin ping으로 실제 DB 연결을 확인합니다."""
    container = resolve_running_container(target["container"]) or target["container"]
    try:
        result = subprocess.run(
            [
                "docker",
                "exec",
                *_docker_env(target["root_password"]),
                container,
                "mysqladmin",
                "ping",
                "-h",
                "localhost",
                "-uroot",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def count_database_rows(target: Mapping[str, str]) -> tuple[int, str]:
    """각 테이블의 COUNT(*)를 합산해 정확한 논리 행 수를 측정합니다."""
    container = resolve_running_container(target["container"]) or target["container"]
    db_name = target["db_name"].replace("`", "``")
    list_command = [
        "docker",
        "exec",
        *_docker_env(target["root_password"]),
        container,
        "mysql",
        "-uroot",
        "-s",
        "-N",
        "-e",
        "SELECT TABLE_NAME FROM information_schema.tables WHERE TABLE_SCHEMA='"
        + target["db_name"].replace("'", "''")
        + "' AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME;",
    ]
    try:
        tables = subprocess.run(
            list_command, capture_output=True, text=True, check=True, timeout=30
        ).stdout.splitlines()
        total = 0
        for table in tables:
            escaped_table = table.replace("`", "``")
            query = f"SELECT COUNT(*) FROM `{db_name}`.`{escaped_table}`;"
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    *_docker_env(target["root_password"]),
                    container,
                    "mysql",
                    "-uroot",
                    "-s",
                    "-N",
                    "-e",
                    query,
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=120,
            )
            value = result.stdout.strip()
            if not value.isdigit():
                raise ValueError(f"행 수 응답이 숫자가 아닙니다: {table}")
            total += int(value)
        return total, "COUNT(*) per table"
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0, "unavailable"


def dump_database(target: Mapping[str, str]) -> dict[str, Any]:
    """MySQL dirty-page 정합성을 확보한 뒤 gzip 스트리밍 덤프를 생성합니다."""
    container = resolve_running_container(target["container"])
    if not container:
        raise DatabaseExportError(f"컨테이너가 실행 중이 아닙니다: {target['container']}")

    db_name = target["db_name"]
    output_path = Path(target["output_file"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    row_count, row_source = count_database_rows(target)
    view_meta = inspect_view_definers(target, container)
    invalid_view_definers = find_invalid_view_definers(target, container, view_meta)
    if invalid_view_definers:
        output_path.unlink(missing_ok=True)
        details = ", ".join(
            f"{view.get('table_name', '<unknown>')} ({view.get('definer', '<unknown>')})"
            for view in invalid_view_definers
        )
        raise DatabaseExportError(
            f"invalid View DEFINER가 있어 무손실 dump를 생성할 수 없습니다: {details}"
        )
    dump_args = [
        "mysqldump",
        "-uroot",
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
    dump_command = " ".join(shlex.quote(value) for value in dump_args)
    # mysql CLI를 오래 유지해 FLUSH TABLES lock의 세션을 dump 종료까지 보존합니다.
    # 별도의 `mysql -e` 프로세스로 lock을 걸면 프로세스 종료와 함께 lock이 풀리므로
    # named pipe를 통해 FLUSH/DUMP/UNLOCK 경계를 하나의 mysql 세션에 유지합니다.
    session_script = (
        "set -eu; "
        "lock_dir=$(mktemp -d); lock_pipe=${lock_dir}/mysql-session; mkfifo ${lock_pipe}; "
        "lock_pid=0; "
        "cleanup() { "
        "if [ ${lock_pid} -ne 0 ]; then printf 'UNLOCK TABLES;\\nQUIT;\\n' >${lock_pipe} || true; wait ${lock_pid} || true; fi; "
        "rm -rf ${lock_dir}; "
        "}; trap cleanup EXIT; "
        "mysql -uroot <${lock_pipe} >/dev/null 2>&1 & lock_pid=$!; "
        "exec 3>${lock_pipe}; printf 'FLUSH TABLES WITH READ LOCK;\\n' >&3; sleep 1; "
        f"{dump_command}; "
        "printf 'UNLOCK TABLES;\\nQUIT;\\n' >&3; exec 3>&-; wait ${lock_pid}; lock_pid=0"
    )
    command = [
        "docker",
        "exec",
        *_docker_env(target["root_password"]),
        "-i",
        container,
        "sh",
        "-c",
        session_script,
    ]

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
