#!/usr/bin/env python3
"""Docker named-volume snapshot, promote, and rollback implementation.

모든 live volume 쓰기는 ``STAGING_VALIDATED`` 이후에만 허용된다.  backup
archive 생성이 성공하지 않으면 promote를 시작하지 않으며, cutover 후 검증
실패 시 동일한 archive를 사용해 target volume을 복구한다.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Any, Iterable

try:
    from .restore_state import MigrationState, MigrationStateManager
except ImportError:  # direct execution from migration_pack/scripts
    from restore_state import MigrationState, MigrationStateManager


class RecoveryError(RuntimeError):
    """Docker snapshot 또는 cutover 실패."""


TAR_IMAGE = os.environ.get("MIGRATION_TAR_IMAGE", "ubuntu:24.04")
ROLLBACK_BUDGET_SECONDS = 15 * 60


@dataclass(frozen=True)
class DatabaseTarget:
    name: str
    live_volume: str
    staging_volume: str
    dump_file: str
    row_counts: dict[str, int]


def _run(command: list[str], *, timeout: float = 900, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Docker command를 실행하되 stdout/stderr를 호출자 로그로 흘리지 않는다."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=env, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RecoveryError(f"Docker 작업을 실행할 수 없습니다(type={type(exc).__name__})") from exc
    if result.returncode != 0:
        raise RecoveryError(f"Docker 작업 실패(code={result.returncode})")
    return result


def build_snapshot_command(volume: str, archive: Path, image: str = TAR_IMAGE) -> list[str]:
    archive = archive.resolve()
    return [
        "docker", "run", "--rm", "--mount", f"type=volume,src={volume},dst=/source,readonly",
        "--mount", f"type=bind,src={archive.parent},dst=/backup",
        image, "tar", "--sparse", "-czf", f"/backup/{archive.name}", "-C", "/source", ".",
    ]


def build_restore_command(volume: str, archive: Path, image: str = TAR_IMAGE) -> list[str]:
    archive = archive.resolve()
    return [
        "docker", "run", "--rm", "--mount", f"type=volume,src={volume},dst=/target",
        "--mount", f"type=bind,src={archive.parent},dst=/backup,readonly",
        image, "sh", "-c", "rm -rf /target/./* /target/.[!.]* /target/..?* 2>/dev/null || true; tar -xzf /backup/" + archive.name + " -C /target",
    ]


class MigrationRecovery:
    """Run-scoped recovery coordinator for the two canonical databases."""

    def __init__(self, databases: list[DatabaseTarget], *, pack_root: Path, run_id: str = "migration") -> None:
        self.databases = databases
        self.pack_root = pack_root.resolve()
        self.run_id = run_id
        self.backup_dir = self.pack_root / "staging" / run_id / "backup"
        self.state = MigrationStateManager(run_id=run_id, state_file=self.pack_root / "staging" / run_id / "state.json")
        self.backup_refs: dict[str, Path] = {}
        self.staging_containers: dict[str, str] = {}
        self.live_containers: dict[str, str] = {}
        self.staging_root_passwords: dict[str, str] = {}
        self.promoted = False

    @classmethod
    def from_manifest(cls, manifest_path: Path, *, pack_root: Path | None = None, run_id: str = "migration") -> "MigrationRecovery":
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        databases = [
            DatabaseTarget(
                name=str(entry["name"]),
                live_volume=str(entry["live_volume"]),
                staging_volume=str(entry["staging_volume"]),
                dump_file=str(entry["dump_file"]),
                row_counts={str(key): int(value) for key, value in dict(entry.get("row_counts", {})).items()},
            )
            for entry in manifest.get("databases", [])
        ]
        if {target.name for target in databases} != {"pilos_v2", "oliview_project"}:
            raise RecoveryError("recovery target은 두 canonical database여야 합니다")
        return cls(databases, pack_root=pack_root or manifest_path.parent, run_id=run_id)

    def _create_volume(self, volume: str) -> None:
        _run(["docker", "volume", "create", "--label", f"aiservice.migration.run={self.run_id}", volume], timeout=60)

    def _copy_volume(self, source: str, target: str, *, clear_target: bool = False) -> None:
        clear = "rm -rf /target/./* /target/.[!.]* /target/..?* 2>/dev/null || true; " if clear_target else ""
        _run(
            [
                "docker", "run", "--rm",
                "--mount", f"type=volume,src={source},dst=/source,readonly",
                "--mount", f"type=volume,src={target},dst=/target",
                TAR_IMAGE, "sh", "-c", clear + "tar -cf - -C /source . | tar -xf - -C /target",
            ],
            timeout=900,
        )

    def _start_stopped_live_containers(self) -> None:
        for container in self.live_containers.values():
            state = subprocess.run(
                ["docker", "inspect", "--format={{.State.Running}}", container],
                capture_output=True, text=True, check=False,
            ).stdout.strip().lower()
            if state != "true":
                _run(["docker", "start", container], timeout=60)

    def create_backup(self, volume: str) -> Path:
        """live named volume을 read-only tar snapshot으로 보존한다."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        archive = self.backup_dir / f"{volume}.tar.gz"
        _run(build_snapshot_command(volume, archive))
        if not archive.is_file() or archive.stat().st_size == 0:
            raise RecoveryError("backup archive가 생성되지 않았습니다")
        self.backup_refs[volume] = archive
        return archive

    def create_staging(self, targets: Iterable[dict[str, str]] | None = None) -> None:
        """Create, start, and restore run-scoped MySQL staging containers.

        No live volume is mounted writable in this phase.
        """
        if self.state.state == MigrationState.CREATED:
            self.state.transition_to(MigrationState.PREFLIGHT_PASSED, reason="recovery preflight accepted")
        if self.state.state == MigrationState.PREFLIGHT_PASSED:
            self.state.transition_to(MigrationState.STAGING_IN_PROGRESS, reason="creating isolated staging resources")
        target_map = {target.name: target for target in self.databases}
        for raw in targets or []:
            name = str(raw["db_name"])
            target = target_map.get(name)
            if target is None:
                continue
            staging_volume = str(raw.get("staging_volume") or target.staging_volume)
            container = str(raw.get("staging_container") or f"aiservice-staging-{self.run_id}-{name}")
            self._create_volume(staging_volume)
            self.staging_containers[name] = container
            self.live_containers[name] = str(raw.get("container", name))
            self.staging_root_passwords[name] = str(raw["root_password"])
            _run(
                [
                    "docker", "run", "-d", "--name", container,
                    "--mount", f"type=volume,src={staging_volume},dst=/var/lib/mysql",
                    "-e", f"MYSQL_DATABASE={name}",
                    "-e", f"MYSQL_USER={raw['user']}",
                    "-e", f"MYSQL_PASSWORD={raw['password']}",
                    "-e", f"MYSQL_ROOT_PASSWORD={raw['root_password']}",
                    "mysql:8.0",
                ],
                timeout=120,
            )
            if not self._wait_for_mysql(container, str(raw["root_password"])):
                self.discard_staging()
                raise RecoveryError(f"staging MySQL 기동 실패(database={name})")
            self._restore_dump(container, name, str(raw["user"]), str(raw["password"]), Path(raw["dump_path"]))
        if not self.staging_containers:
            for target in self.databases:
                self._create_volume(target.staging_volume)
                self.staging_containers[target.name] = f"aiservice-staging-{self.run_id}-{target.name}"
                raise RecoveryError("staging target credentials are required for restore")
        if self.state.state == MigrationState.STAGING_IN_PROGRESS:
            self.state.transition_to(MigrationState.STAGING_RESTORED, reason="run-scoped staging volumes created")

    @staticmethod
    def _wait_for_mysql(container: str, root_password: str, retries: int = 60) -> bool:
        for _ in range(retries):
            result = subprocess.run(
                ["docker", "exec", "-e", f"MYSQL_PWD={root_password}", container, "mysqladmin", "ping", "-h", "localhost", "-uroot"],
                capture_output=True, text=True, check=False,
            )
            if result.returncode == 0:
                return True
            time.sleep(2)
        return False

    @staticmethod
    def _restore_dump(container: str, database: str, user: str, password: str, dump_path: Path) -> None:
        if not dump_path.is_file():
            raise RecoveryError(f"staging dump가 없습니다(database={database})")
        command = ["docker", "exec", "-i", "-e", f"MYSQL_PWD={password}", container, "mysql", f"-u{user}", "--default-character-set=utf8mb4", database]
        try:
            import gzip
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            assert process.stdin is not None
            with gzip.open(dump_path, "rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    process.stdin.write(chunk)
            process.stdin.close()
            if process.wait() != 0:
                raise RecoveryError(f"staging dump 복원 실패(database={database})")
        except (OSError, BrokenPipeError) as exc:
            raise RecoveryError(f"staging dump 스트리밍 실패(database={database})") from exc

    def _mysql_validation(self, target: DatabaseTarget) -> bool:
        container = self.staging_containers.get(target.name)
        if not container:
            return False
        command = ["docker", "exec"]
        root_password = self.staging_root_passwords.get(target.name, "")
        if root_password:
            command.extend(["-e", f"MYSQL_PWD={root_password}"])
        command.extend([container, "mysqladmin", "ping", "-h", "localhost", "-uroot"])
        result = _run(command, timeout=30)
        return result.returncode == 0

    def validate_staging(self, targets: Iterable[dict[str, str]] | None = None) -> None:
        """staging container readiness 및 manifest 대상 DB 존재를 확인한다."""
        if self.state.state != MigrationState.STAGING_RESTORED:
            raise RecoveryError("staging validation은 STAGING_RESTORED 뒤에만 가능합니다")
        if not all(self._mysql_validation(target) for target in self.databases):
            self.discard_staging()
            raise RecoveryError("staging MySQL readiness 검증 실패")
        del targets
        self.state.transition_to(MigrationState.STAGING_VALIDATED, reason="staging database validation passed")

    def _ensure_backups(self) -> None:
        for target in self.databases:
            if target.live_volume not in self.backup_refs:
                self.create_backup(target.live_volume)

    def promote(self) -> dict[str, Any]:
        """backup 성공 후 staging 내용을 canonical live volume으로 cut over한다."""
        if self.state.state != MigrationState.STAGING_VALIDATED:
            raise RecoveryError("promote는 STAGING_VALIDATED 뒤에만 가능합니다")
        self._ensure_backups()
        self.state.assert_can_write_live_volume()
        promoted_volumes: list[str] = []
        candidates: dict[str, str] = {}
        live_write_started = False
        try:
            # Prepare every candidate while live services remain untouched.
            for target in self.databases:
                candidate = f"{target.live_volume}.__candidate_{self.run_id}"
                candidates[target.name] = candidate
                self._create_volume(candidate)
                self._copy_volume(target.staging_volume, candidate)

            # Detach database consumers before modifying their mounted volumes.
            for container in self.live_containers.values():
                _run(["docker", "stop", "--time", "30", container], timeout=60)

            # Preserve named-volume identity so Compose references remain stable.
            # Backup-based rollback covers the unavoidable sequential update of
            # the two independent Docker volumes.
            for target in self.databases:
                live_write_started = True
                self._copy_volume(candidates[target.name], target.live_volume, clear_target=True)
                _run(["docker", "volume", "rm", candidates[target.name]], timeout=120)
                promoted_volumes.append(target.live_volume)
            self._start_stopped_live_containers()
            self.promoted = True
            self.state.transition_to(MigrationState.PROMOTED, reason="validated staging promoted to canonical live volumes")
            return {"status": "PROMOTED", "volumes": promoted_volumes, "backup_refs": {key: str(value) for key, value in self.backup_refs.items()}}
        except RecoveryError:
            if live_write_started:
                self.rollback(reason="post-cutover promote failure")
            raise

    def rollback(self, *, reason: str = "post-cutover validation failure") -> dict[str, Any]:
        """backup archive를 live volume에 복원하고 15분 budget을 강제한다."""
        started = time.monotonic()
        if not self.backup_refs:
            raise RecoveryError("rollback backup이 없습니다")
        restored: list[str] = []
        try:
            for target in self.databases:
                archive = self.backup_refs.get(target.live_volume)
                if archive is None:
                    raise RecoveryError("DB별 backup이 없습니다")
                remaining = max(1.0, ROLLBACK_BUDGET_SECONDS - (time.monotonic() - started))
                _run(build_restore_command(target.live_volume, archive), timeout=remaining)
                restored.append(target.live_volume)
                if time.monotonic() - started > ROLLBACK_BUDGET_SECONDS:
                    raise RecoveryError("rollback 15분 budget 초과")
            self._start_stopped_live_containers()
            if self.state.state in {MigrationState.PROMOTED, MigrationState.TUNNEL_DEGRADED}:
                self.state.transition_to(MigrationState.ROLLED_BACK, reason=reason)
            return {"status": "ROLLED_BACK", "restored_volumes": restored, "rollback_duration_seconds": round(time.monotonic() - started, 3)}
        except RecoveryError:
            raise

    def verify_post_cutover(self, check: Callable[[], bool] | None = None) -> bool:
        """Run post-cutover checks and rollback immediately on failure."""

        containers = list(self.live_containers.values()) or list(self.staging_containers.values())
        passed = bool(check()) if check is not None else all(
            subprocess.run(
                ["docker", "inspect", "--format={{.State.Running}}", str(container)],
                capture_output=True, text=True, check=False,
            ).stdout.strip().lower() == "true"
            for container in containers
        )
        if passed and self.state.state == MigrationState.PROMOTED:
            self.state.transition_to(MigrationState.VERIFIED, reason="post-cutover verification passed")
            return True
        if self.state.state == MigrationState.PROMOTED:
            self.state.transition_to(MigrationState.TUNNEL_DEGRADED, reason="post-cutover verification failed")
            self.rollback(reason="post-cutover verification failed")
        return False

    def discard_staging(self) -> None:
        for target in self.databases:
            container = self.staging_containers.get(target.name)
            if container:
                subprocess.run(["docker", "rm", "-f", container], capture_output=True, text=True, check=False)
            subprocess.run(["docker", "volume", "rm", target.staging_volume], capture_output=True, text=True, check=False)
        if self.state.state in {MigrationState.STAGING_IN_PROGRESS, MigrationState.STAGING_RESTORED, MigrationState.STAGING_VALIDATED}:
            self.state.transition_to(MigrationState.STAGING_DISCARDED, reason="staging validation failed")
