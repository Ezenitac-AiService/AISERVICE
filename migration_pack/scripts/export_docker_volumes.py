#!/usr/bin/env python3
"""Docker named volume의 일관성 보장 sparse 아카이브 생성기."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

def _ensure_docker_host() -> None:
    if sys.platform.startswith("win") and "DOCKER_HOST" not in os.environ:
        try:
            res = subprocess.run(["docker", "info"], capture_output=True, timeout=3, check=False)
            if res.returncode != 0:
                wsl_res = subprocess.run(["wsl", "-d", "Ubuntu", "--", "hostname", "-I"], capture_output=True, text=True, timeout=5, check=False)
                if wsl_res.returncode == 0 and wsl_res.stdout.strip():
                    ip = wsl_res.stdout.split()[0]
                    os.environ["DOCKER_HOST"] = f"tcp://{ip}:2375"
        except Exception:
            pass

_ensure_docker_host()

class VolumeExportError(RuntimeError):
    """필수 볼륨을 안전하게 추출할 수 없을 때 발생합니다."""


TAR_IMAGE = os.environ.get("MIGRATION_TAR_IMAGE", "ubuntu:24.04")
CHROMA_HELPER_IMAGE = os.environ.get("MIGRATION_CHROMA_HELPER_IMAGE", "python:3.12-slim")


def get_managed_volumes_map() -> dict[str, dict[str, Any]]:
    """canonical volume 이름과 source Compose 스택 매핑을 반환합니다."""
    return {
        "ateam_db_data": {
            "description": "A-Team Pilos MySQL 8.0 Data Volume",
            "associated_container": "pilos-db",
            "service": "pilos_v2",
            "snapshot": "mysql",
        },
        "bteam_bteam_mysql_data": {
            "description": "B-Team Oliview MySQL 8.0 Data Volume",
            "associated_container": "bteam_db",
            "service": "oliview_project",
            "snapshot": "mysql",
        },
        "green_mysql_data": {
            "description": "B-Team Green MySQL 8.0 Data Volume",
            "associated_container": "mysql-green",
            "service": "green_mysql",
            "snapshot": "mysql",
        },
        "green_chroma_data": {
            "description": "B-Team Green ChromaDB v2 Vector Storage",
            "associated_container": "chroma-green",
            "service": "chromadb_v2",
            "snapshot": "chroma",
        },
        "aiservice_redis_data": {
            "description": "AISERVICE Common Redis 7 Session & Cache",
            "associated_container": "aiservice-redis",
            "service": "redis",
            "snapshot": "redis",
        },
    }


def list_existing_docker_volumes() -> list[str]:
    try:
        result = subprocess.run(
            ["docker", "volume", "ls", "--format", "{{.Name}}"],
            capture_output=True,
            text=True,
            check=True,
        )
        return [value.strip() for value in result.stdout.splitlines() if value.strip()]
    except (OSError, subprocess.CalledProcessError):
        return []


def resolve_existing_volume_name(name: str, container: str | None = None) -> str:
    """Compose 접두사가 붙은 실제 Docker volume 이름을 canonical 이름에서 찾습니다."""
    if not name:
        return name
    if container:
        try:
            result = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "-f",
                    "{{range .Mounts}}{{println .Name \"|\" .Destination}}{{end}}",
                    container,
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            mount_names = []
            for line in result.stdout.splitlines():
                volume, separator, destination = line.partition("|")
                if separator and destination.strip() == "/data" and volume.strip():
                    mount_names.append(volume.strip())
            matches = sorted(value for value in mount_names if name in value)
            if matches:
                return matches[0]
        except (OSError, subprocess.SubprocessError):
            pass
    existing = set(list_existing_docker_volumes())
    if name in existing:
        return name
    matches = sorted(
        value for value in existing if value.endswith(name) or name in value
    )
    return matches[0] if matches else name


def resolve_running_container(name_or_service: str) -> str | None:
    """정확한 이름, Compose 접두사/접미사 및 라벨 기반으로 실행 중인 컨테이너를 탐색합니다."""
    if not name_or_service:
        return None
    # 1. 정확한 이름 검사
    if _container_running(name_or_service):
        return name_or_service

    # 2. docker ps 실행 중 컨테이너 목록에서 라벨/이름 패턴 탐색
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

            # 서비스 라벨 매칭 (com.docker.compose.service)
            if f"com.docker.compose.service={name_or_service}" in c_labels:
                return c_name
            # 이름 접두/접미 패턴 매칭 (e.g. aiservice-mysql-green-1, bteam_mysql-green_1)
            clean_target = name_or_service.replace("-", "").replace("_", "")
            clean_cname = c_name.replace("-", "").replace("_", "")
            if clean_target in clean_cname:
                return c_name
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _container_running(container: str) -> bool:
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", container],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip().lower() == "true"


def measure_chroma_vector_count(container: str, vol_name: str = "green_chroma_data") -> int:
    """Chroma canonical collection의 원본 vector 수를 SQLite 또는 지원 컨테이너에서 측정합니다."""
    script = (
        "import os, sqlite3\n"
        "c = 0\n"
        "if os.path.exists('/data/chroma.sqlite3'):\n"
        "    try:\n"
        "        con = sqlite3.connect('/data/chroma.sqlite3')\n"
        "        col = con.execute(\"SELECT id FROM collections WHERE name='oliview_review_sentences_v2'\").fetchone()\n"
        "        if col:\n"
        "            r = con.execute('SELECT COUNT(*) FROM embeddings e JOIN segments s ON e.segment_id=s.id WHERE s.collection=?', (col[0],)).fetchone()\n"
        "            c = r[0] if r else 0\n"
        "        else:\n"
        "            r = con.execute('SELECT COUNT(*) FROM embeddings').fetchone()\n"
        "            c = r[0] if r else 0\n"
        "        con.close()\n"
        "    except Exception:\n"
        "        pass\n"
        "print(c)\n"
    )
    # 1. 타겟 컨테이너 내부 실행 시도
    if container and _container_running(container):
        for py_cmd in ["python3", "python"]:
            result = subprocess.run(
                ["docker", "exec", container, py_cmd, "-c", script],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip().isdigit():
                return int(result.stdout.strip())

    # 2. 컨테이너에 python/sqlite3 CLI가 없는 경우 볼륨 마운트 헬퍼 컨테이너 fallback
    helper_volume = resolve_existing_volume_name(vol_name, container)
    helper_result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{helper_volume}:/data:ro",
            CHROMA_HELPER_IMAGE,
            "python",
            "-c",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if helper_result.returncode == 0 and helper_result.stdout.strip().isdigit():
        return int(helper_result.stdout.strip())

    raise VolumeExportError(f"Chroma vector 수 측정 실패: container={container}, volume={vol_name}")


def _run_chroma_sqlite_command(
    container: str, volume_name: str, script: str, *, read_only: bool
) -> subprocess.CompletedProcess[str]:
    """실행 중 컨테이너 또는 지원 Python 컨테이너에서 Chroma SQLite 작업을 실행합니다."""
    if container and _container_running(container):
        for py_cmd in ["python3", "python"]:
            result = subprocess.run(
                ["docker", "exec", container, py_cmd, "-c", script],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if result.returncode == 0:
                return result

    mount_volume = resolve_existing_volume_name(volume_name, container)
    mount = f"{mount_volume}:/data" + (":ro" if read_only else "")
    return subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            mount,
            CHROMA_HELPER_IMAGE,
            "python",
            "-c",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


def pre_flush_service_state(vol_name: str, meta: dict[str, Any]) -> dict[str, Any]:
    """MySQL/Chroma는 pause, Redis는 BGSAVE 후 상태를 반환합니다."""
    raw_container = str(meta.get("associated_container", ""))
    container = resolve_running_container(raw_container) or raw_container
    state = {"paused": False, "resolved_container": container}
    if not container or not _container_running(container):
        if meta.get("snapshot") == "chroma":
            raise VolumeExportError(f"Chroma 컨테이너가 실행 중이 아닙니다: {raw_container}")
        return state

    snapshot = str(meta.get("snapshot", ""))
    if snapshot == "redis":
        result = subprocess.run(
            ["docker", "exec", container, "redis-cli", "BGSAVE"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            raise VolumeExportError(f"Redis BGSAVE 실패: {container}")
        deadline = time.time() + 30
        while time.time() < deadline:
            check = subprocess.run(
                ["docker", "exec", container, "redis-cli", "INFO", "persistence"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if (
                check.returncode == 0
                and "rdb_bgsave_in_progress:0" in check.stdout
                and "rdb_last_bgsave_status:ok" in check.stdout.lower()
            ):
                return state
            time.sleep(1)
        raise VolumeExportError(f"Redis BGSAVE 완료 대기 시간 초과: {container}")

    if snapshot == "chroma":
        checkpoint_script = (
            "import os, sqlite3\n"
            "if os.path.exists('/data/chroma.sqlite3'):\n"
            "    try:\n"
            "        con = sqlite3.connect('/data/chroma.sqlite3')\n"
            "        con.execute('PRAGMA wal_checkpoint(TRUNCATE)')\n"
            "        con.close()\n"
            "    except Exception:\n"
            "        pass\n"
            "print('ok')\n"
        )
        checkpoint = _run_chroma_sqlite_command(
            container, vol_name, checkpoint_script, read_only=False
        )
        if checkpoint.returncode != 0:
            raise VolumeExportError(f"Chroma SQLite WAL checkpoint 실패: {container}")
        first_count = measure_chroma_vector_count(container, vol_name)
        second_count = measure_chroma_vector_count(container, vol_name)
        if first_count != second_count:
            raise VolumeExportError(
                f"Chroma vector 수가 안정화되지 않았습니다: {first_count} != {second_count}"
            )
        meta["vector_count"] = first_count

    # pause는 MySQL/Chroma의 추가 변경을 막는 일관성 경계를 제공합니다.
    result = subprocess.run(
        ["docker", "pause", container],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        raise VolumeExportError(f"서비스 pause 실패: {container}")
    state["paused"] = True

    return state


def post_resume_service_state(
    vol_name: str, meta: dict[str, Any], state: dict[str, bool] | None = None
) -> None:
    del vol_name
    container = str((state or {}).get("resolved_container") or meta.get("associated_container", ""))
    if container and (state or {}).get("paused"):
        subprocess.run(
            ["docker", "unpause", container],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )


def export_single_volume(
    volume_name: str,
    output_dir: Path | str,
    meta: dict[str, Any] | None = None,
    *,
    archive_name: str | None = None,
) -> tuple[Path, int, str]:
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    archive_stem = archive_name or volume_name
    archive_file = out_dir / f"{archive_stem}.tar.gz"
    state: dict[str, Any] = {"paused": False}
    if meta:
        state = pre_flush_service_state(volume_name, meta)
    try:
        command = build_volume_archive_command(volume_name, archive_file.name, out_dir)
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=900, check=False
        )
        if result.returncode != 0:
            raise VolumeExportError(
                f"volume tar 실패({volume_name}): {result.stderr[-1000:]}"
            )
        if not archive_file.is_file():
            raise VolumeExportError(f"아카이브가 생성되지 않았습니다: {archive_file}")
        digest = hashlib.sha256(archive_file.read_bytes()).hexdigest()
        return archive_file, archive_file.stat().st_size, digest
    finally:
        if meta:
            post_resume_service_state(volume_name, meta, state)


def build_volume_archive_command(
    volume_name: str, archive_name: str, output_dir: Path | str
) -> list[str]:
    """실제 Docker 호스트 경로와 sparse-capable GNU tar image를 사용하는 명령을 구성합니다."""
    host_mount = str(Path(output_dir).resolve())
    return [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{volume_name}:/source:ro",
        "-v",
        f"{host_mount}:/backup",
        TAR_IMAGE,
        "tar",
        "--sparse",
        "-czf",
        f"/backup/{archive_name}",
        "-C",
        "/source",
        ".",
    ]


def export_all_managed_volumes(
    output_dir: Path | str, *, strict: bool = True
) -> list[dict[str, Any]]:
    existing = set(list_existing_docker_volumes())
    volume_map = get_managed_volumes_map()
    results: list[dict[str, Any]] = []
    missing: list[str] = []
    for canonical_name, meta in volume_map.items():
        source_name = canonical_name
        if source_name not in existing:
            matches = sorted(
                v
                for v in existing
                if v == canonical_name or v in canonical_name or canonical_name in v
            )
            if matches:
                source_name = matches[0]
            else:
                missing.append(canonical_name)
                continue
        archive_path, size_bytes, digest = export_single_volume(
            source_name, output_dir, meta, archive_name=canonical_name
        )
        if canonical_name == "green_chroma_data" and not isinstance(
            meta.get("vector_count"), int
        ):
            raise VolumeExportError(
                "green_chroma_data의 canonical vector 수 측정 없이 아카이브를 생성할 수 없습니다"
            )
        results.append(
            {
                "volume_name": canonical_name,
                "source_volume_name": source_name,
                "archive_file": f"volumes/{archive_path.name}",
                "size_bytes": size_bytes,
                "sha256": digest,
                "is_sparse": True,
            }
        )
        if "vector_count" in meta:
            results[-1]["vector_count"] = int(meta["vector_count"])
    if missing and strict:
        raise VolumeExportError("필수 Docker volume 누락: " + ", ".join(missing))
    return results


if __name__ == "__main__":
    export_all_managed_volumes(Path(__file__).resolve().parent.parent / "volumes")
