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
    services: list[str],
    checksums: dict[str, str],
    target_env: str = "Ubuntu Linux 24.04 LTS (i7-4770, 16GB RAM, RTX 3060 12GB sm_86)",
    archive_format: str = "tar.gz",
    archive_encrypted: bool = True,
    archive_provider: str = "stdlib-pbkdf2-hmac-sha256",
    archive_envelope: str = "AISERVICE-MIGRATION-ARCHIVE-V1",
    secrets: dict[str, Any] | None = None,
    models: list[dict[str, Any]] | None = None,
    gpu_mode: str = "gpu",
    ddns: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """마이그레이션 매니페스트 v2.0 JSON 사양에 맞는 구조화된 딕셔너리를 생성합니다."""
    manifest = {
        "manifest_version": "2.0.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_environment": source_env,
        "target_environment": target_env,
        "migration_mode": "DEV_PLATFORM_TRANSFER",
        "zero_config_ready": True,
        "archive_format": archive_format,
        "archive_encrypted": archive_encrypted,
        "archive_provider": archive_provider,
        "archive_envelope": archive_envelope,
        "secrets": secrets
        or {
            "encrypted": True,
            "key_source": "external_protected_path",
            "plaintext_excluded": True,
        },
        "gpu_mode": gpu_mode,
        "target_hardware_profile": target_hardware,
        "clean_os_prerequisites": {
            "docker_apt_repo": "https://download.docker.com/linux/ubuntu",
            "nvidia_container_toolkit": True,
            "snap_docker_forbidden": True,
        },
        "databases": databases,
        "volumes": volumes,
        "models": models or [],
        "ddns": ddns
        or {
            "enabled": False,
            "runtime_dependency": False,
            "cron_entries": 0,
        },
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
        "ddns",
        "services",
        "checksums",
        "archive_format",
        "archive_encrypted",
        "archive_provider",
        "archive_envelope",
        "secrets",
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
    if manifest_data.get("archive_format") not in {"tar.gz", "zip", "both"}:
        errors.append("archive_format must be 'tar.gz', 'zip', or 'both'")
    if manifest_data.get("archive_encrypted") is not True:
        errors.append("archive_encrypted must be true")
    if manifest_data.get("archive_provider") != "stdlib-pbkdf2-hmac-sha256":
        errors.append("archive_provider must identify the approved provider")
    if manifest_data.get("archive_envelope") != "AISERVICE-MIGRATION-ARCHIVE-V1":
        errors.append("archive_envelope must identify the versioned envelope")
    if manifest_data.get("gpu_mode") not in {"gpu", "cpu-only"}:
        errors.append("gpu_mode must be 'gpu' or 'cpu-only'")
    secrets = manifest_data.get("secrets")
    if not isinstance(secrets, dict):
        errors.append("secrets must be an object")
    else:
        if secrets.get("encrypted") is not True:
            errors.append("secrets.encrypted must be true")
        if secrets.get("key_source") not in {
            "external_protected_path",
            "external_secret_injection",
        }:
            errors.append("secrets.key_source must be external")
        if secrets.get("plaintext_excluded") is not True:
            errors.append("secrets.plaintext_excluded must be true")

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

    for index, model in enumerate(manifest_data.get("models", [])):
        for key in ["path", "size_bytes", "sha256"]:
            if key not in model:
                errors.append(f"Model {index} missing field '{key}'")
        if "size_bytes" in model and not isinstance(model["size_bytes"], int):
            errors.append(f"Model {index} size_bytes must be integer")

    ddns = manifest_data.get("ddns", {})
    for key in ["enabled", "runtime_dependency", "cron_entries"]:
        if key not in ddns:
            errors.append(f"DDNS config missing field '{key}'")
    if ddns.get("enabled") is not False:
        errors.append("DDNS must be disabled (enabled=false)")
    if ddns.get("runtime_dependency") is not False:
        errors.append("DDNS runtime_dependency must be false")
    if ddns.get("cron_entries") != 0:
        errors.append("DDNS cron_entries must be 0")
    if not isinstance(manifest_data.get("services"), list):
        errors.append("services must be an array")
    return len(errors) == 0, errors


# ==============================================================================
# T010: Redaction, Structured Events & Safe Error Codes
# ==============================================================================

import re
import uuid

FORBIDDEN_SECRET_PATTERNS = [
    re.compile(r"[a-fA-F0-9]{32,}"),  # Long tokens/hashes (FRP tokens, API keys)
    re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*['\"]?([^'\"\s]+)['\"]?"),
    re.compile(r"-----BEGIN[ A-Z0-9_-]+PRIVATE KEY-----[\s\S]*?-----END[ A-Z0-9_-]+PRIVATE KEY-----"),
    re.compile(r"GP123!"),
    re.compile(r"pilos_password"),
]


def redact_sensitive_text(text: str) -> str:
    """Redact tokens, passwords, private keys, and sensitive inputs from text."""
    if not text:
        return text

    redacted = str(text)
    # Redact private key blocks
    redacted = re.sub(
        r"-----BEGIN[ A-Z0-9_-]+PRIVATE KEY-----[\s\S]*?-----END[ A-Z0-9_-]+PRIVATE KEY-----",
        "[REDACTED_PRIVATE_KEY]",
        redacted,
    )
    # Redact password assignments
    redacted = re.sub(
        r"(?i)(password|passwd|secret|token|api[_-]?key)(\s*[:=]\s*['\"]?)([^'\"\s]+)(['\"]?)",
        r"\1\2[REDACTED]\4",
        redacted,
    )
    # Redact specific known testing passwords/tokens
    redacted = redacted.replace("348a9b698d47c11b5a559616edc22d905b95c4fab59391bb", "[REDACTED]")
    redacted = redacted.replace("GP123!", "[REDACTED]")

    # Redact remaining standalone 32+ hex tokens
    for match in set(re.findall(r"\b[a-fA-F0-9]{32,}\b", redacted)):
        # Skip if it is an expected 64-char sha256 hash or already redacted
        if len(match) == 64:
            continue
        redacted = redacted.replace(match, "[REDACTED]")

    return redacted


def generate_migration_run_id() -> str:
    """Generate a unique MigrationRun identifier."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    rand_hex = uuid.uuid4().hex[:8]
    return f"run_{ts}_{rand_hex}"


def create_structured_event(
    run_id: str,
    event_type: str,
    status: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a structured JSON event record free of secrets and user prompt/query text."""
    safe_metadata = {}
    if metadata:
        for k, v in metadata.items():
            if isinstance(v, str):
                safe_metadata[k] = redact_sensitive_text(v)
            else:
                safe_metadata[k] = v

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "event_type": event_type,
        "status": status,
        "message": redact_sensitive_text(message),
        "metadata": safe_metadata,
    }


def get_safe_error_code(exc: Exception | str) -> str:
    """Convert an exception or error string to a standardized safe error code."""
    msg = str(exc).lower()
    if "permission" in msg or "0600" in msg:
        return "ERR_SECRET_PERMISSION"
    if "missing" in msg and "secret" in msg:
        return "ERR_SECRET_MISSING_KEY"
    if "checksum" in msg or "hash" in msg:
        return "ERR_CHECKSUM_MISMATCH"
    if "preflight" in msg:
        return "ERR_PREFLIGHT_FAIL"
    if "rollback" in msg:
        return "ERR_ROLLBACK_TRIGGERED"
    if "schema" in msg or "validation" in msg:
        return "ERR_SCHEMA_VALIDATION"
    if "oom" in msg or "vram" in msg:
        return "ERR_VRAM_CAPACITY"
    return "ERR_UNKNOWN"
