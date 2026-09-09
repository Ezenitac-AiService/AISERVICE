#!/usr/bin/env python3
"""안전한 AISERVICE DEMO 복원 오케스트레이터.

이 모듈은 checksum/manifest 검증과 staging 복원의 진입점이다. live volume은
staging 검증과 backup 생성이 끝난 뒤에만 별도의 recovery 모듈을 통해 접근한다.
비밀값은 외부 보호 파일에서만 읽으며 로그와 보고서에는 상태·식별자만 남긴다.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
PACK_ROOT = SCRIPT_DIR.parent
PROJECT_ROOT = PACK_ROOT.parent
DB_DIR = PACK_ROOT / "database"


class RestoreError(RuntimeError):
    """복원 단계 실패와 외부 계약 종료 코드를 함께 전달한다."""

    def __init__(self, message: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def log_info(message: str) -> None:
    print(f"[INFO] {message}")


def log_warn(message: str) -> None:
    print(f"[WARN] {message}", file=sys.stderr)


def log_error(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value.strip().strip('"').strip("'")
    return values


def _validate_secret_file(path: Path) -> None:
    if not path.is_file():
        raise RestoreError("외부 secret 파일이 없습니다", 1)
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode != 0o600:
        raise RestoreError("외부 secret 파일 권한은 0600이어야 합니다", 1)
    if os.name == "posix" and os.geteuid() == 0 and path.stat().st_uid != 0:
        raise RestoreError("외부 secret 파일 소유자는 root여야 합니다", 1)


def load_environment(project_root: Path | str, secret_file: Path | str | None = None) -> dict[str, str]:
    """비밀 없는 프로젝트 설정과 외부 secret을 병합한다.

    우선순위는 process environment > external secret file > project `.env`다.
    값 자체는 호출자에게 반환되지만 이 모듈은 이를 출력하거나 report에 넣지 않는다.
    """
    root = Path(project_root)
    values = _parse_env_file(root / ".env")
    if secret_file:
        protected = Path(secret_file)
        _validate_secret_file(protected)
        values.update(_parse_env_file(protected))
    values.update({key: value for key, value in os.environ.items() if key.isupper()})
    return values


def required_environment(env: Mapping[str, str], required: list[str]) -> list[str]:
    missing: list[str] = []
    for key in required:
        value = env.get(key, "").strip()
        if not value or value.startswith("__SET_IN_PROTECTED"):
            missing.append(key)
    return missing


def _safe_pack_path(pack_root: Path, relative_path: str) -> Path:
    candidate = (pack_root / relative_path).resolve()
    root = pack_root.resolve()
    if candidate != root and root not in candidate.parents:
        raise RestoreError("manifest 경로가 pack root 밖을 가리킵니다", 2)
    return candidate


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksums(
    checksum_path: Path | str | None = None,
    pack_root: Path | str | None = None,
) -> bool:
    """checksums.sha256를 안전한 pack-relative 경로로 검증한다."""
    root = Path(pack_root or PACK_ROOT).resolve()
    checksum_file = Path(checksum_path) if checksum_path else root / "database" / "checksums.sha256"
    if not checksum_file.is_absolute():
        checksum_file = root / checksum_file
    checksum_file = checksum_file.resolve()
    if not checksum_file.is_file():
        log_error("checksums.sha256가 없습니다")
        return False

    entries = 0
    valid = True
    for line_number, raw_line in enumerate(checksum_file.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64 or any(char not in "0123456789abcdefABCDEF" for char in parts[0]):
            log_error(f"checksum 형식 오류(line={line_number})")
            valid = False
            continue
        expected, relative = parts
        if relative.startswith("*"):
            relative = relative[1:]
        try:
            target = _safe_pack_path(root, relative)
        except RestoreError:
            valid = False
            continue
        entries += 1
        if not target.is_file() or _hash_file(target) != expected.lower():
            log_error(f"checksum 불일치 또는 파일 누락(path={relative})")
            valid = False
    if entries == 0:
        log_error("검증할 checksum 항목이 없습니다")
        return False
    return valid


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RestoreError(f"JSON artifact를 읽을 수 없습니다: {path.name}", 2) from exc
    if not isinstance(value, dict):
        raise RestoreError(f"JSON object가 필요합니다: {path.name}", 2)
    return value


def _load_migration_manifest(pack_root: Path) -> dict[str, Any]:
    manifest = _load_json(pack_root / "migration_manifest.json")
    if manifest.get("manifest_version") != "1.1.0":
        raise RestoreError("지원하지 않는 migration manifest 버전입니다", 2)
    if manifest.get("asset_manifest_file") != "asset_manifest.json":
        raise RestoreError("asset manifest 참조가 정본과 다릅니다", 2)
    databases = manifest.get("databases")
    if not isinstance(databases, list) or {item.get("name") for item in databases} != {"pilos_v2", "oliview_project"}:
        raise RestoreError("복원 대상 DB는 두 개여야 합니다", 2)
    return manifest


def get_restore_targets(
    project_root: Path | str = PROJECT_ROOT,
    *,
    pack_root: Path | str | None = None,
    secret_file: Path | str | None = None,
) -> list[dict[str, str]]:
    """manifest와 환경 주입값으로 두 canonical DB staging target을 만든다."""
    root = Path(project_root)
    pack = Path(pack_root or root / "migration_pack")
    manifest = _load_migration_manifest(pack)
    env = load_environment(root, secret_file)
    required = [
        "PILOS_DB_USER",
        "PILOS_DB_PASSWORD",
        "PILOS_DB_ROOT_PASSWORD",
        "BTEAM_DB_USER",
        "BTEAM_DB_PASSWORD",
        "BTEAM_DB_ROOT_PASSWORD",
    ]
    missing = required_environment(env, required)
    if missing:
        raise RestoreError("필수 DB secret key가 누락되었습니다", 1)

    by_name = {str(item["name"]): item for item in manifest["databases"]}
    definitions = [
        ("pilos_v2", "PILOS_DB_CONTAINER", "pilos-db", "PILOS_DB_USER", "PILOS_DB_PASSWORD", "PILOS_DB_ROOT_PASSWORD", "ateam_db_data"),
        ("oliview_project", "BTEAM_DB_CONTAINER", "bteam_db", "BTEAM_DB_USER", "BTEAM_DB_PASSWORD", "BTEAM_DB_ROOT_PASSWORD", "bteam_bteam_mysql_data"),
    ]
    targets: list[dict[str, str]] = []
    for name, container_key, default_container, user_key, password_key, root_password_key, default_volume in definitions:
        record = by_name[name]
        targets.append(
            {
                "container": env.get(container_key, default_container),
                "db_name": name,
                "user": env[user_key],
                "password": env[password_key],
                "root_password": env[root_password_key],
                "volume_name": str(record["live_volume"] or default_volume),
                "staging_volume": str(record["staging_volume"]),
                "staging_container": f"aiservice-staging-{{run_id}}-{name}",
                "dump_path": str(pack / str(record["dump_file"])),
            }
        )
    return targets


def _docker_password_args(password: str) -> list[str]:
    return ["-e", f"MYSQL_PWD={password}"]


def wait_for_mysql(container: str, password: str, max_retries: int = 60) -> bool:
    for _ in range(max_retries):
        result = subprocess.run(
            ["docker", "exec", *_docker_password_args(password), container, "mysqladmin", "ping", "-h", "localhost", "-uroot"],
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
        result = subprocess.run(["docker", "exec", container, "redis-cli", "ping"], capture_output=True, text=True, check=False)
        if result.returncode == 0 and "PONG" in result.stdout.upper():
            return True
        time.sleep(2)
    return False


def wait_for_model_gateway(url: str, max_retries: int = 60) -> bool:
    for _ in range(max_retries):
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return True
        except (OSError, urllib.error.URLError):
            time.sleep(2)
    return False


def wait_for_http(url: str, max_retries: int = 60) -> bool:
    return wait_for_model_gateway(url, max_retries)


def check_mysql_has_data(container: str, user: str, password: str, db_name: str) -> bool:
    query = "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s;" % json.dumps(db_name)
    result = subprocess.run(
        ["docker", "exec", *_docker_password_args(password), container, "mysql", f"-u{user}", "-s", "-N", "-e", query],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip().isdigit() and int(result.stdout.strip()) > 0


def restore_database_dump(container: str, db_name: str, user: str, password: str, dump_path: Path | str) -> bool:
    path = Path(dump_path)
    if not path.is_file():
        log_error(f"논리 DB dump가 없습니다(database={db_name})")
        return False
    command = ["docker", "exec", *_docker_password_args(password), "-i", container, "mysql", f"-u{user}", "--default-character-set=utf8mb4", db_name]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        assert process.stdin is not None
        with gzip.open(path, "rb") as stream:
            shutil.copyfileobj(stream, process.stdin, length=1024 * 1024)
        process.stdin.close()
        return_code = process.wait()
        if return_code:
            log_error(f"논리 DB 복원 실패(database={db_name}, code={return_code})")
        return return_code == 0
    except (BrokenPipeError, OSError) as exc:
        process.kill()
        log_error(f"논리 DB 스트리밍 실패(database={db_name}, type={type(exc).__name__})")
        return False


def restore_databases_to_staging(targets: list[dict[str, str]]) -> None:
    """두 DB를 live volume이 아닌 staging container로 복원한다."""
    for target in targets:
        if not restore_database_dump(
            target["staging_container"], target["db_name"], target["user"], target["password"], target["dump_path"]
        ):
            raise RestoreError(f"staging DB 복원 실패(database={target['db_name']})", 3)


def _compose_up(services: list[str], *, compose_file: Path, cwd: Path) -> None:
    result = subprocess.run(["docker", "compose", "-f", str(compose_file), "up", "-d", *services], cwd=cwd, check=False)
    if result.returncode:
        raise RestoreError("Docker Compose 기동 실패", 4)


def _safe_extract_archive(archive: Path, extract_to: Path) -> None:
    extract_to = extract_to.resolve()
    extract_to.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip" or archive.name.endswith(".zip.enc"):
        with zipfile.ZipFile(archive) as bundle:
            members = [Path(name) for name in bundle.namelist()]
            if any(member.is_absolute() or ".." in member.parts for member in members):
                raise RestoreError("archive path traversal가 감지되었습니다", 2)
            bundle.extractall(extract_to)
        return
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            target = (extract_to / member.name).resolve()
            if target != extract_to and extract_to not in target.parents:
                raise RestoreError("archive path traversal가 감지되었습니다", 2)
        bundle.extractall(extract_to)


def _write_dry_run_report(report_path: Path, state: str, run_id: str, *, error_code: str | None = None) -> None:
    payload: dict[str, Any] = {
        "run_id": run_id,
        "mode": "DEMO",
        "state": state,
        "secret_values_logged": False,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if error_code:
        payload["error_code"] = error_code
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AISERVICE Ubuntu Restore Engine")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--pack-root", type=Path, default=PACK_ROOT)
    # Keep argparse's public contract string-like; convert to Path at the
    # boundary in main().  This also makes shell/CI callers portable.
    parser.add_argument("--secret-file", required=True)
    parser.add_argument("--report", type=Path, default=PACK_ROOT / "verification_report.json")
    parser.add_argument("--yes", "-y", action="store_true")
    parser.add_argument("--force-dump", action="store_true")
    parser.add_argument("--dry-run", "-d", action="store_true")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--extract-to", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    run_id = f"run_{time.strftime('%Y%m%d_%H%M%S', time.gmtime())}"
    pack_root = args.pack_root.resolve()
    try:
        secret_file = Path(args.secret_file).resolve()
        _validate_secret_file(secret_file)
        if args.archive:
            if not args.extract_to:
                raise RestoreError("--archive 사용 시 --extract-to가 필요합니다", 2)
            _safe_extract_archive(args.archive.resolve(), args.extract_to)
        manifest = _load_migration_manifest(pack_root)
        if not verify_checksums(pack_root=pack_root):
            _write_dry_run_report(args.report, "ABORTED", run_id, error_code="ERR_CHECKSUM_MISMATCH")
            return 2
        if args.dry_run:
            _write_dry_run_report(args.report, "CHECKSUMS_VERIFIED", run_id)
            log_info(f"dry-run 검증 완료(databases={len(manifest['databases'])})")
            return 0

        if not shutil.which("docker"):
            raise RestoreError("Docker Engine이 없습니다", 4)
        targets = get_restore_targets(args.project_root, pack_root=pack_root, secret_file=secret_file)
        if not args.yes:
            raise RestoreError("실제 live 전환은 --yes 승인과 backup 검증이 필요합니다", 3)
        from snapshot_recovery import MigrationRecovery

        recovery = MigrationRecovery.from_manifest(pack_root / "migration_manifest.json", pack_root=pack_root)
        for target in targets:
            target["staging_container"] = target["staging_container"].replace("{run_id}", recovery.run_id)
        recovery.create_staging(targets)
        recovery.validate_staging(targets)
        recovery.promote()
        if not recovery.verify_post_cutover():
            raise RestoreError("post-cutover 검증 실패로 rollback을 수행했습니다", 3)
        recovery.discard_staging()
        _write_dry_run_report(args.report, "PROMOTED", run_id)
        return 0
    except RestoreError as exc:
        log_error(str(exc))
        _write_dry_run_report(args.report, "ABORTED", run_id, error_code=f"ERR_{exc.exit_code}")
        return exc.exit_code
    except (OSError, ValueError, KeyError) as exc:
        log_error(f"복원 실패(type={type(exc).__name__})")
        _write_dry_run_report(args.report, "ABORTED", run_id, error_code="ERR_RESTORE")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
