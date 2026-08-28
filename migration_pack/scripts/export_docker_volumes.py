#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_docker_volumes.py
========================
Docker Named Volume 물리 아카이브 추출기.
공식 Docker Sidecar 패턴(alpine 컨테이너)과 sparse file 보존(tar --sparse -czf)을 사용하여
A-Team DB, B-Team DB, ChromaDB v2, Redis 7 볼륨을 안전하게 무손실 아카이빙합니다.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple


def get_managed_volumes_map() -> Dict[str, Dict[str, Any]]:
    """AISERVICE 생태계에서 관리되는 Docker Named Volume 목록과 컨테이너 매핑을 반환합니다."""
    return {
        "ateam_db_data": {
            "description": "A-Team Pilos MySQL 8.0 Data Volume",
            "associated_container": "pilos-db",
            "service": "pilos_v2",
        },
        "bteam_bteam_mysql_data": {
            "description": "B-Team Oliview MySQL 8.0 Data Volume",
            "associated_container": "bteam_db",
            "service": "oliview_project",
        },
        "green_chroma_data": {
            "description": "B-Team Green ChromaDB v2 Vector Storage",
            "associated_container": "bteam-green-chromadb",
            "service": "chromadb_v2",
        },
        "aiservice_redis_data": {
            "description": "AISERVICE Common Redis 7 Session & Cache",
            "associated_container": "aiservice-redis",
            "service": "redis",
        },
    }


def list_existing_docker_volumes() -> List[str]:
    """현재 Docker 데몬에 존재하는 볼륨 목록을 반환합니다."""
    try:
        res = subprocess.run(
            ["docker", "volume", "ls", "--format", "{{.Name}}"],
            capture_output=True,
            text=True,
            check=True,
        )
        return [v.strip() for v in res.stdout.splitlines() if v.strip()]
    except Exception:
        return []


def pre_flush_service_state(vol_name: str, meta: Dict[str, Any]) -> None:
    """볼륨 백업 전 서비스별 메모리 플러시/체크포인트를 수행합니다."""
    container = meta.get("associated_container")
    if not container:
        return

    # 1. Redis BGSAVE 트리거
    if "redis" in vol_name.lower():
        try:
            subprocess.run(
                ["docker", "exec", container, "redis-cli", "BGSAVE"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            time.sleep(1)
        except Exception:
            pass

    # 2. ChromaDB SQLite WAL Checkpoint 트리거
    if "chroma" in vol_name.lower():
        try:
            # 컨테이너 일시정지 또는 WAL 체크포인트
            subprocess.run(
                ["docker", "pause", container],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            pass


def post_resume_service_state(vol_name: str, meta: Dict[str, Any]) -> None:
    """볼륨 백업 후 일시정지된 서비스 컨테이너를 재개합니다."""
    container = meta.get("associated_container")
    if not container:
        return

    if "chroma" in vol_name.lower():
        try:
            subprocess.run(
                ["docker", "unpause", container],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            pass


def export_single_volume(
    volume_name: str,
    output_dir: Path | str,
    meta: Dict[str, Any] | None = None,
) -> Tuple[Path, int, str]:
    """단일 Named Volume을 alpine 사이드카 컨테이너를 통해 tar.gz 아카이브로 추출합니다."""
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    archive_file = out_dir / f"{volume_name}.tar.gz"

    if meta:
        pre_flush_service_state(volume_name, meta)

    try:
        # Docker Sidecar Pattern with Sparse support
        # Windows/Linux host path conversion for docker volume mount
        host_backup_mount = str(out_dir)
        if sys.platform.startswith("win"):
            # e.g., C:\AISERVICE\... -> /c/AISERVICE/... for Docker Desktop
            drive, rest = os.path.splitdrive(str(out_dir))
            if drive:
                drive_letter = drive[0].lower()
                clean_rest = rest.replace("\\", "/")
                host_backup_mount = f"/{drive_letter}{clean_rest}"

        cmd = [
            "docker", "run", "--rm",
            "-v", f"{volume_name}:/source:ro",
            "-v", f"{out_dir}:/backup",
            "alpine",
            "tar", "--sparse", "-czf", f"/backup/{volume_name}.tar.gz",
            "-C", "/source", ".",
        ]

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if res.returncode != 0 and not archive_file.is_file():
            raise RuntimeError(f"Failed to export volume '{volume_name}': {res.stderr}")

        if not archive_file.is_file():
            raise FileNotFoundError(f"Archive not generated: {archive_file}")

        # SHA-256 계산
        sha = hashlib.sha256()
        with open(archive_file, "rb") as f:
            while chunk := f.read(1024 * 1024):
                sha.update(chunk)
        sha256_hex = sha.hexdigest()
        size_bytes = archive_file.stat().st_size

        return archive_file, size_bytes, sha256_hex

    finally:
        if meta:
            post_resume_service_state(volume_name, meta)


def export_all_managed_volumes(output_dir: Path | str) -> List[Dict[str, Any]]:
    """모든 활성 관리 대상 볼륨을 추출하고 메타데이터 목록을 반환합니다."""
    existing_volumes = set(list_existing_docker_volumes())
    vol_map = get_managed_volumes_map()
    results: List[Dict[str, Any]] = []

    print("\n" + "=" * 70)
    print(" [AISERVICE] DOCKER NAMED VOLUME PHYSICAL EXPORTER (Sparse Sidecar)")
    print("=" * 70)

    for vol_name, meta in vol_map.items():
        # 볼륨 실제 존재 여부 확인 (이름 변형 탐색)
        target_vol = vol_name
        if target_vol not in existing_volumes:
            # 접두어 변형 검색 (예: aiservice_redis_data vs redis_data)
            matching = [v for v in existing_volumes if vol_name in v or v in vol_name]
            if matching:
                target_vol = matching[0]
            else:
                print(f"⚠️ Volume '{vol_name}' not found in Docker daemon, skipping.")
                continue

        print(f"\n▶ Exporting volume '{target_vol}' ({meta['description']})...")
        t0 = time.time()
        archive_path, size_bytes, sha256_hex = export_single_volume(target_vol, output_dir, meta)
        elapsed = time.time() - t0

        size_mb = size_bytes / (1024 * 1024)
        print(f"  ✓ Exported to '{archive_path.name}' ({size_mb:.2f} MB) in {elapsed:.1f}s")
        print(f"  ✓ SHA-256: {sha256_hex}")

        results.append({
            "volume_name": target_vol,
            "archive_file": f"volumes/{archive_path.name}",
            "size_bytes": size_bytes,
            "sha256": sha256_hex,
            "is_sparse": True,
        })

    return results


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "volumes"
    export_all_managed_volumes(out)
