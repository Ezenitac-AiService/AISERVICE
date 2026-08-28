#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
manifest_utils.py
=================
마이그레이션 매니페스트 v2.0 및 SHA-256 체크섬 생성, 검증, 스키마 유효성 검사 유틸리티.
Python 3 표준 라이브러리(hashlib, json, os, sys)만을 사용하여 0-dependency 보장.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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
    files: List[Tuple[Path | str, str]],
    output_checksums_path: Path | str,
) -> Dict[str, str]:
    """
    파일 목록에 대한 SHA-256 해시를 계산하고 standard sha256sum 포맷으로 저장합니다.
    (예: `<hash>  <relative_path>`)
    """
    out_path = Path(output_checksums_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    checksum_map: Dict[str, str] = {}
    lines: List[str] = []

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
) -> Tuple[bool, List[str], List[str]]:
    """
    checksums.sha256 파일을 읽어 각 파일의 무결성을 검증합니다.
    Returns: (is_all_valid, matched_files, mismatched_files)
    """
    cs_path = Path(checksums_file_path)
    base = Path(base_dir)
    if not cs_path.is_file():
        return False, [], [f"Checksums file missing: {cs_path}"]

    matched: List[str] = []
    mismatched: List[str] = []

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
                mismatched.append(f"{rel_path} (Hash mismatch: expected {expected_hash}, got {actual_hash})")

    is_valid = len(mismatched) == 0 and len(matched) > 0
    return is_valid, matched, mismatched


def build_manifest_v2(
    source_env: Dict[str, Any],
    target_hardware: Dict[str, Any],
    databases: List[Dict[str, Any]],
    volumes: List[Dict[str, Any]],
    ddns_config: Dict[str, Any],
    services: List[str],
    checksums: Dict[str, str],
    target_env: str = "Ubuntu Linux 24.04 LTS (i7-930 Nehalem, 24GB RAM, GTX 1070 8GB sm_61)",
) -> Dict[str, Any]:
    """마이그레이션 매니페스트 v2.0 JSON 사양에 맞는 구조화된 딕셔너리를 생성합니다."""
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
        "ddns_config": ddns_config,
        "services": services,
        "checksums": checksums,
    }
    return manifest


def validate_manifest_schema(manifest_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
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
    errors: List[str] = []

    for k in required_keys:
        if k not in manifest_data:
            errors.append(f"Missing required manifest field: '{k}'")

    if manifest_data.get("manifest_version") != "2.0.0":
        errors.append(f"Unsupported manifest version: {manifest_data.get('manifest_version')} (Expected '2.0.0')")

    hw = manifest_data.get("target_hardware_profile", {})
    for hw_k in ["cpu", "gpu", "ram_mb", "vram_mb", "llama_cpp_flags"]:
        if hw_k not in hw:
            errors.append(f"Missing hardware profile field: '{hw_k}'")

    return len(errors) == 0, errors
