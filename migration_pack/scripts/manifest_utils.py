#!/usr/bin/env python3
"""
manifest_utils.py
=================
마이그레이션 매니페스트 v2.0 및 SHA-256 체크섬 생성, 검증, 스키마 유효성 검사 유틸리티.
Python 3 표준 라이브러리(hashlib, json, os, sys)만을 사용하여 0-dependency 보장.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def calculate_sha256(file_path: Path | str, chunk_size: int = 65536) -> str:
    """단일 파일의 SHA-256 해시를 스트리밍 방식으로 계산합니다."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found for hashing: {path}")

    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        for byte_block in iter(lambda: f.read(chunk_size), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def generate_checksums_file(
    files: list[tuple[Path | str, str]],
    output_checksums_path: Path | str,
) -> dict[str, str]:
    """
    파일 목록에 대한 SHA-256 해시를 계산하고 standard sha256sum 포맷으로 저장합니다.
    (예: `<hash>  <relative_path>`)
    """
    out_path = Path(output_checksums_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    checksum_map: dict[str, str] = {}
    lines: list[str] = []

    for file_path, rel_name in files:
        fpath = Path(file_path)
        if fpath.exists():
            h = calculate_sha256(fpath)
            checksum_map[rel_name] = h
            # GNU coreutils sha256sum compatibility: 2 spaces
            lines.append(f"{h}  {rel_name}")

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")

    return checksum_map


def verify_checksums_file(
    checksums_file_path: Path | str,
    base_dir: Path | str,
) -> tuple[bool, list[str], list[str]]:
    """
    checksums.sha256 파일을 읽어 각 파일의 무결성을 검증합니다.
    Returns: (is_all_valid, matched_files, mismatched_files)
    """
    cs_path = Path(checksums_file_path)
    base = Path(base_dir)
    if not cs_path.is_file():
        return False, [], [f"Checksums file missing: {cs_path}"]

    matched: list[str] = []
    mismatched: list[str] = []

    with open(cs_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(maxsplit=1)
            if len(parts) != 2:
                continue
            expected_hash, rel_path = parts[0], parts[1].strip()
            target_file = base / rel_path
            if not target_file.is_file():
                mismatched.append(f"{rel_path} (Missing)")
                continue

            actual_hash = calculate_sha256(target_file)
            if actual_hash.lower() == expected_hash.lower():
                matched.append(rel_path)
            else:
                mismatched.append(
                    f"{rel_path} (Hash mismatch: expected {expected_hash}, got {actual_hash})"
                )

    is_valid = len(mismatched) == 0 and len(matched) > 0
    return is_valid, matched, mismatched


def build_manifest_v2(
    source_env: dict[str, Any],
    target_hardware: dict[str, Any],
    databases: list[dict[str, Any]],
    volumes: list[dict[str, Any]],
    ddns_config: dict[str, Any],
    services: list[str],
    checksums: dict[str, str],
    target_env: str = "Ubuntu Linux 24.04 LTS (i7-930 Nehalem, 24GB RAM, GTX 1070 8GB sm_61)",
) -> dict[str, Any]:
    """마이그레이션 매니페스트 v2.0 JSON 사양에 맞는 구조화된 딕셔너리를 생성합니다."""
    safe_ddns = dict(ddns_config)
    token = str(safe_ddns.get("token", ""))
    if token and "***" not in token and token != "<unset>":
        safe_ddns["token"] = (
            f"{token[:2]}***{token[-2:]}" if len(token) > 4 else "*" * len(token)
        )
    manifest = {
        "manifest_version": "2.0.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_environment": source_env,
        "target_environment": target_env,
        "migration_mode": "DEV_PLATFORM_TRANSFER",
        "zero_config_ready": True,
        "target_hardware_profile": target_hardware,
        "clean_os_prerequisites": {
            "docker_apt_repo": "https://download.docker.com/linux/ubuntu",
            "nvidia_container_toolkit": True,
            "snap_docker_forbidden": True,
        },
        "databases": databases,
        "volumes": volumes,
        "ddns_config": safe_ddns,
        "services": services,
        "checksums": checksums,
    }
    return manifest


def validate_manifest_schema(manifest_data: dict[str, Any]) -> tuple[bool, list[str]]:
    """매니페스트 v2.0의 필수 키 및 타입 제약조건을 검증합니다."""
    required_keys = [
        "manifest_version",
        "created_at",
        "source_environment",
        "target_environment",
        "migration_mode",
        "zero_config_ready",
        "target_hardware_profile",
        "databases",
        "volumes",
        "ddns_config",
        "services",
        "checksums",
    ]
    errors: list[str] = []

    for k in required_keys:
        if k not in manifest_data:
            errors.append(f"Missing required manifest field: '{k}'")

    if manifest_data.get("manifest_version") != "2.0.0":
        errors.append(
            f"Unsupported manifest version: {manifest_data.get('manifest_version')} (Expected '2.0.0')"
        )

    if manifest_data.get("migration_mode") != "DEV_PLATFORM_TRANSFER":
        errors.append("migration_mode must be 'DEV_PLATFORM_TRANSFER'")
    if not isinstance(manifest_data.get("zero_config_ready"), bool):
        errors.append("zero_config_ready must be boolean")

    hw = manifest_data.get("target_hardware_profile", {})
    for hw_k in ["cpu", "gpu", "ram_mb", "vram_mb", "llama_cpp_flags"]:
        if hw_k not in hw:
            errors.append(f"Missing hardware profile field: '{hw_k}'")
    for field in ["ram_mb", "vram_mb"]:
        if field in hw and not isinstance(hw[field], int):
            errors.append(f"Hardware field '{field}' must be integer")

    for index, database in enumerate(manifest_data.get("databases", [])):
        for key in ["name", "dump_file", "size_bytes", "sha256", "row_count"]:
            if key not in database:
                errors.append(f"Database {index} missing field '{key}'")
    for index, volume in enumerate(manifest_data.get("volumes", [])):
        for key in ["volume_name", "archive_file", "size_bytes", "sha256"]:
            if key not in volume:
                errors.append(f"Volume {index} missing field '{key}'")

    ddns = manifest_data.get("ddns_config", {})
    for key in ["domain", "token", "cron_interval_minutes"]:
        if key not in ddns:
            errors.append(f"DDNS config missing field '{key}'")
    if "cron_interval_minutes" in ddns and not isinstance(
        ddns["cron_interval_minutes"], int
    ):
        errors.append("cron_interval_minutes must be integer")
    if not isinstance(manifest_data.get("services"), list):
        errors.append("services must be an array")
    if not isinstance(manifest_data.get("checksums"), dict):
        errors.append("checksums must be an object")

    return len(errors) == 0, errors
