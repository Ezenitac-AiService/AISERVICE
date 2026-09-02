#!/usr/bin/env python3
"""환경 변수 기반 MySQL 안전 스트리밍 덤프 생성기."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone

# Windows Console UTF-8 safety
if sys.platform.startswith("win"):
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


def dump_database(target: dict) -> tuple[int, str]:
    db = target["db_name"]
    container = target["container"]
    user = target["user"]
    pw = target["password"]
    out_path = target["output_file"]

    cmd = [
        "docker", "exec", container,
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
        db,
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
