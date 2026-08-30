#!/usr/bin/env python3
"""Docker named volume의 일관성 보장 sparse 아카이브 생성기."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


class VolumeExportError(RuntimeError):
    """필수 볼륨을 안전하게 추출할 수 없을 때 발생합니다."""


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


def _container_running(container: str) -> bool:
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", container],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip().lower() == "true"


def measure_chroma_vector_count(container: str) -> int:
    """Chroma canonical collection의 원본 vector 수를 SQLite에서 측정합니다."""
    script = (
        "import sqlite3; "
        "db=sqlite3.connect('/data/chroma.sqlite3'); "
        "collection=db.execute(\"SELECT id FROM collections WHERE name='oliview_review_sentences_v2'\").fetchone(); "
        "raise SystemExit(3) if collection is None else None; "
        "print(db.execute('SELECT COUNT(*) FROM embeddings WHERE collection_id=?', (collection[0],)).fetchone()[0]); "
        "db.close()"
    )
    result = subprocess.run(
        ["docker", "exec", container, "python", "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip().isdigit():
        raise VolumeExportError(f"Chroma vector 수 측정 실패: {container}")
    return int(result.stdout.strip())


def pre_flush_service_state(vol_name: str, meta: dict[str, Any]) -> dict[str, bool]:
    """MySQL/Chroma는 pause, Redis는 BGSAVE 후 상태를 반환합니다."""
    container = str(meta.get("associated_container", ""))
    state = {"paused": False}
    if not container or not _container_running(container):
        if meta.get("snapshot") == "chroma":
            raise VolumeExportError(f"Chroma 컨테이너가 실행 중이 아닙니다: {container}")
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
                timeout=5,
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

    # pause는 MySQL dirty page의 추가 변경을 막는 일관성 경계를 제공합니다.
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

    if snapshot == "chroma":
        try:
            checkpoint = subprocess.run(
                [
                    "docker",
                    "exec",
                    container,
                    "python",
                    "-c",
                    (
                        "import pathlib, sqlite3; "
                        "p=pathlib.Path('/data/chroma.sqlite3'); "
                        "con=sqlite3.connect(p); "
                        "result=con.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchall(); "
                        "con.close(); "
                        "busy=result[0][0] if result else 0; "
                        "raise SystemExit(1) if busy else SystemExit(0)"
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if checkpoint.returncode != 0:
                raise VolumeExportError(f"Chroma SQLite WAL checkpoint 실패: {container}")
            first_count = measure_chroma_vector_count(container)
            second_count = measure_chroma_vector_count(container)
            if first_count != second_count:
                raise VolumeExportError(
                    f"Chroma vector 수가 안정화되지 않았습니다: {first_count} != {second_count}"
                )
            meta["vector_count"] = first_count
        except Exception:
            subprocess.run(
                ["docker", "unpause", container],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            state["paused"] = False
            raise
    return state


def post_resume_service_state(
    vol_name: str, meta: dict[str, Any], state: dict[str, bool] | None = None
) -> None:
    del vol_name
    container = str(meta.get("associated_container", ""))
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
    state: dict[str, bool] = {"paused": False}
    if meta:
        state = pre_flush_service_state(volume_name, meta)
    try:
        host_mount = str(out_dir)
        if sys.platform.startswith("win"):
            drive, rest = str(out_dir)[:2], str(out_dir)[2:]
            if drive[1:] == ":":
                host_mount = f"/{drive[0].lower()}{rest.replace(chr(92), '/')}"
        command = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{volume_name}:/source:ro",
            "-v",
            f"{host_mount}:/backup",
            "alpine",
            "tar",
            "--sparse",
            "-czf",
            f"/backup/{archive_file.name}",
            "-C",
            "/source",
            ".",
        ]
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
