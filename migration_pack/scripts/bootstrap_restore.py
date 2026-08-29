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
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from migration_pack.scripts.env_utils import load_environment, required_environment
from migration_pack.scripts.export_docker_volumes import get_managed_volumes_map

SCRIPT_DIR = Path(__file__).resolve().parent
PACK_ROOT = SCRIPT_DIR.parent
PROJECT_ROOT = PACK_ROOT.parent
DB_DIR = PACK_ROOT / "database"
VOL_DIR = PACK_ROOT / "volumes"


class RestoreError(RuntimeError):
    def __init__(self, message: str, exit_code: int = 3):
        super().__init__(message)
        self.exit_code = exit_code


def log_info(message: str) -> None:
    print(f"[INFO] {message}")


def log_warn(message: str) -> None:
    print(f"[WARN] {message}")


def log_error(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_checksum_path(rel_path: str) -> Path:
    normalized = rel_path.replace("/", os.sep)
    if rel_path.startswith(("database/", "volumes/")):
        return PACK_ROOT / normalized
    return PROJECT_ROOT / normalized


def verify_checksums() -> bool:
    checksum_file = PACK_ROOT / "checksums.sha256"
    if not checksum_file.is_file():
        checksum_file = DB_DIR / "checksums.sha256"
    if not checksum_file.is_file():
        log_warn("checksums.sha256가 없어 무결성 검증을 건너뜁니다.")
        return True

    valid = True
    for raw_line in checksum_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            valid = False
            log_error(f"잘못된 checksum 행: {line[:80]}")
            continue
        expected, rel_path = parts
        target = _resolve_checksum_path(rel_path.strip())
        if not target.is_file():
            valid = False
            log_error(f"checksum 대상 누락: {rel_path}")
            continue
        actual = _sha256(target)
        if actual.lower() != expected.lower():
            valid = False
            log_error(f"checksum 불일치: {rel_path}")
    return valid


def _docker_mount_path(path: Path) -> str:
    resolved = str(path.resolve())
    if os.name != "nt":
        return resolved
    drive, rest = resolved[:2], resolved[2:]
    if drive[1:] == ":":
        return f"/{drive[0].lower()}{rest.replace(chr(92), '/')}"
    return resolved.replace("\\", "/")


def check_preflight_system(project_root: Path | str = PROJECT_ROOT) -> tuple[bool, list[str]]:
    """Root 권한, 포트 충돌(80, 8080, 3306, 6379), 최소 25GB 디스크 여유 공간을 검사합니다."""
    issues: list[str] = []
    root = Path(project_root).resolve()

    # 1. Root 권한 검사 (POSIX)
    if os.name != "nt" and hasattr(os, "geteuid") and os.geteuid() != 0:
        issues.append("Root 또는 sudo 권한이 필요합니다 (sudo ./bootstrap_restore.sh)")

    # 2. 디스크 여유 공간 검사 (최소 25GB)
    try:
        free_bytes = shutil.disk_usage(root).free
        if free_bytes < 25 * 1024**3:
            issues.append(f"디스크 여유 공간 부족: {free_bytes / (1024**3):.1f}GB < 25GB")
    except OSError as exc:
        issues.append(f"디스크 공간 확인 실패: {exc}")

    # 3. 포트 충돌 검사 (80, 8080, 3306, 6379)
    check_ports = [80, 8080, 3306, 6379]
    for port in check_ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                # 바인드 테스트로 로컬 충돌 확인
                s.bind(("0.0.0.0", port))
        except OSError:
            # 포트가 이미 점유된 경우
            issues.append(
                f"포트 {port}가 이미 사용 중입니다. 충돌 프로세스를 종료하거나 .env에서 포트를 재매핑하십시오."
            )

    return len(issues) == 0, issues


def restore_docker_volumes(
    *, force: bool = False, prompt: bool = True, force_dump: bool = False
) -> dict[str, bool]:
    """canonical volume archive를 복원하고 tar 실행 성공을 기록합니다."""
    results: dict[str, bool] = {}
    if force_dump:
        log_info("--force-dump 지정으로 물리 volume 복원을 생략하고 논리 SQL 덤프 복원으로 진행합니다.")
        return results
    if not VOL_DIR.is_dir():
        return results
    archives = sorted(VOL_DIR.glob("*.tar.gz"))
    if not archives:
        return results

    existing_result = subprocess.run(
        ["docker", "volume", "ls", "--format", "{{.Name}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    existing = (
        set(existing_result.stdout.splitlines())
        if existing_result.returncode == 0
        else set()
    )
    for archive in archives:
        canonical = archive.name.removesuffix(".tar.gz")
        if canonical not in get_managed_volumes_map():
            log_warn(f"관리 대상이 아닌 volume archive를 건너뜁니다: {archive.name}")
            continue
        already_exists = canonical in existing
        if already_exists and not force:
            approved = False
            if prompt:
                try:
                    approved = input(
                        f"Docker volume {canonical}을 덮어쓸까요? [y/N] "
                    ).strip().lower() in {"y", "yes"}
                except EOFError:
                    approved = False
            if not approved:
                log_error(
                    f"기존 volume 덮어쓰기 승인이 없어 복원을 중단합니다: {canonical}"
                )
                results[canonical] = False
                continue
        try:
            if already_exists and force:
                # 기존 볼륨 잔여 파일 원자적 초기화
                subprocess.run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "-v",
                        f"{canonical}:/target",
                        "alpine",
                        "sh",
                        "-c",
                        "rm -rf /target/* /target/..?* /target/.[!.]* 2>/dev/null || true",
                    ],
                    capture_output=True,
                    check=False,
                )
            create = subprocess.run(
                ["docker", "volume", "create", canonical],
                capture_output=True,
                text=True,
                check=False,
            )
            if create.returncode != 0:
                raise RestoreError(f"volume 생성 실패: {canonical}")
            command = [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{canonical}:/target",
                "-v",
                f"{_docker_mount_path(VOL_DIR)}:/backup:ro",
                "alpine",
                "tar",
                "xzf",
                f"/backup/{archive.name}",
                "-C",
                "/target",
            ]
            restored = subprocess.run(
                command, capture_output=True, text=True, timeout=900, check=False
            )
            if restored.returncode != 0:
                raise RestoreError(
                    f"volume 아카이브 추출 실패: {canonical}: {restored.stderr[-500:]}"
                )
            results[canonical] = True
            log_info(f"volume 복원 및 tar 검증 완료: {canonical}")
        except (OSError, subprocess.SubprocessError, RestoreError) as exc:
            results[canonical] = False
            log_error(str(exc))
    return results


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
    # Green DB 지원 (환경 변수 또는 docker-compose.green.yml 연계)
    if "GREEN_DB_NAME" in env:
        targets.append(
            {
                "container": env.get("GREEN_DB_CONTAINER", "mysql-green"),
                "db_name": env["GREEN_DB_NAME"],
                "user": env.get("GREEN_DB_USER", "bteam_green"),
                "password": env.get("GREEN_DB_PASSWORD", ""),
                "root_password": env.get(
                    "GREEN_DB_ROOT_PASSWORD", env.get("GREEN_DB_PASSWORD", "")
                ),
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
    url: str = "http://127.0.0.1:8081/health", max_retries: int = 60
) -> bool:
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


def _compose_up(services: list[str]) -> None:
    command = ["docker", "compose", "up", "-d", *services]
    result = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    force = bool(args.force or args.yes)
    try:
        sys_ok, sys_issues = check_preflight_system(PROJECT_ROOT)
        if not sys_ok:
            for issue in sys_issues:
                if args.dry_run or force:
                    log_warn(f"[PREFLIGHT] {issue}")
                else:
                    log_error(f"[PREFLIGHT] {issue}")
            if not (args.dry_run or force):
                raise RestoreError("사전 시스템 검사 실패: 포트/디스크/권한을 확인하십시오", 1)

        if not verify_checksums() and not force:
            raise RestoreError("checksum 검증 실패", 1)
        targets = get_restore_targets(PROJECT_ROOT)
        if args.dry_run:
            log_info("dry-run: 포트/디스크, checksum, 환경 변수, 복원 대상 사전 검사 완료")
            return 0

        volumes = restore_docker_volumes(
            force=force, prompt=not force, force_dump=args.force_dump
        )
        if any(value is False for value in volumes.values()):
            raise RestoreError("하나 이상의 물리 volume 복원이 실패했습니다", 3)

        _compose_up(["pilos_db", "bteam_db", "redis", "vllm-serv"])
        if not wait_for_mysql(targets[0]["container"], targets[0]["root_password"]):
            raise RestoreError("Pilos MySQL readiness timeout", 2)
        if not wait_for_mysql(targets[1]["container"], targets[1]["root_password"]):
            raise RestoreError("B-Team MySQL readiness timeout", 2)
        if not wait_for_redis():
            raise RestoreError("Redis readiness timeout", 2)
        if not wait_for_model_gateway():
            raise RestoreError("Model Gateway readiness timeout", 2)

        restore_databases(targets, volumes, force_dump=args.force_dump)
        _compose_up(
            [
                "oliview_backend",
                "oliview_frontend",
                "oliview_chatbot_a",
                "oliview_chatbot_b",
                "pilos_web",
                "pilos_worker",
                "gateway",
            ]
        )
        if not args.skip_verification:
            verify_script = SCRIPT_DIR / "verify_migration.py"
            result = subprocess.run(
                [sys.executable, str(verify_script)], cwd=PROJECT_ROOT, check=False
            )
            if result.returncode != 0:
                raise RestoreError("11개 endpoint 검증 게이트 실패", 4)
        return 0
    except RestoreError as exc:
        log_error(str(exc))
        return exc.exit_code
    except (OSError, subprocess.SubprocessError) as exc:
        log_error(f"복원 실행 오류: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
