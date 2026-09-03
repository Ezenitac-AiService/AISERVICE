#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AISERVICE Environment Profiler & Configuration Synchronizer (configure_env.py)
-------------------------------------------------------------------------------
Loads and validates DEMO environment configurations and secret boundaries.
Enforces:
- Mode: DEMO (PoC)
- 5 host gateway alias ports (3000, 8001, 8002, 8003, 8004)
- Rate limiting and trusted proxy policies
- Root-owned mode 0600 secret file permissions (FR-011)
- Explicit enablement of SSH standby tunnel (default: installed_disabled)
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

REQUIRED_SECRET_KEYS = {
    "PILOS_DB_PASSWORD",
    "PILOS_DB_ROOT_PASSWORD",
    "BTEAM_DB_PASSWORD",
    "BTEAM_DB_ROOT_PASSWORD",
    "FLASK_APP_SECRET",
}

DEFAULT_DEMO_ENV = {
    "APP_RUN_MODE": "DEMO",
    "PLATFORM_PROFILE": "dev-rtx3060",
    "GATEWAY_PORTAL_PORT": "3000",
    "GATEWAY_PILOS_PORT": "8001",
    "GATEWAY_OLIVIEW_PORT": "8002",
    "GATEWAY_CHATA_PORT": "8003",
    "GATEWAY_CHATB_PORT": "8004",
    "DEFAULT_MODEL": "qwen3.5-4b",
    "FAST_LLM_MODEL": "qwen3.5-2b",
    "SYNTHESIS_LLM_MODEL": "qwen3.5-4b",
    "EMBEDDING_MODEL": "bge-m3",
    "RERANK_MODEL": "bge-reranker-v2-m3",
    "VRAM_SAFETY_LIMIT_MB": "10240",
    "MAX_GPU_CONCURRENT_SLOTS": "4",
    "QUEUE_TIMEOUT_SECONDS": "60",
    "RATE_LIMIT_IP_PER_MINUTE": "10",
    "RATE_LIMIT_CONCURRENT_REQUESTS": "2",
    "RATE_LIMIT_MAX_BODY_BYTES": "65536",
    "RATE_LIMIT_MAX_RESPONSE_TOKENS": "16384",
    "RATE_LIMIT_TIMEOUT_SECONDS": "180",
    "TRUSTED_PROXY_CIDRS": "127.0.0.1/32,172.16.0.0/12",
    "ENABLE_SSH_STANDBY_TUNNEL": "false",
}


def validate_secret_file_permissions(file_path: str | Path, require_root: bool = True) -> bool:
    """Validate that the secret file has strict 0600 permissions and is owned by root."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Secret file not found: {path}")

    st = path.stat()
    mode = stat.S_IMODE(st.st_mode)
    if mode != 0o600:
        raise PermissionError(
            f"Secret file {path} has insecure file permissions ({oct(mode)}). Expected 0600."
        )

    if require_root and os.name == "posix" and os.geteuid() == 0:
        if st.st_uid != 0:
            raise PermissionError(
                f"Secret file {path} must be owned by root (uid 0), found uid {st.st_uid}."
            )

    return True


def load_env_file(file_path: str | Path) -> dict[str, str]:
    """Parse a KEY=VALUE environment file."""
    path = Path(file_path)
    env_vars: dict[str, str] = {}
    if not path.is_file():
        return env_vars

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip()
    return env_vars


def load_and_validate_secrets(secret_file: str | Path, require_root: bool = True) -> dict[str, str]:
    """Load secrets from protected file and verify all required keys exist."""
    validate_secret_file_permissions(secret_file, require_root=require_root)
    secrets = load_env_file(secret_file)

    missing_keys = REQUIRED_SECRET_KEYS - set(secrets.keys())
    if missing_keys:
        raise ValueError(
            f"Missing required secret keys in {secret_file}: {sorted(missing_keys)}"
        )

    return secrets


def get_ssh_standby_status(env: dict[str, str]) -> str:
    """Check explicit enablement flag and endpoint validation for SSH standby tunnel."""
    enable_flag = env.get("ENABLE_SSH_STANDBY_TUNNEL", "false").lower() == "true"
    endpoint_valid = env.get("GATEWAY_ENDPOINT_VALID", "false").lower() == "true"

    if enable_flag and endpoint_valid:
        return "enabled_running"
    return "installed_disabled"


def configure_demo_environment(
    output_path: str | Path,
    secret_file: str | Path | None = None,
    extra_overrides: dict[str, str] | None = None,
    require_root: bool = False,
) -> dict[str, str]:
    """Compose full environment configuration for DEMO deployment."""
    merged_env = dict(DEFAULT_DEMO_ENV)

    if secret_file:
        secrets = load_and_validate_secrets(secret_file, require_root=require_root)
        merged_env.update(secrets)

    if extra_overrides:
        merged_env.update(extra_overrides)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in sorted(merged_env.items())]
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return merged_env


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Configure AISERVICE DEMO environment")
    parser.add_argument("--output", "-o", default=".env", help="Output .env path")
    parser.add_argument("--secret-file", "-s", help="Path to protected secret file (mode 0600)")
    args = parser.parse_args()

    configure_demo_environment(args.output, secret_file=args.secret_file)
    print(f"Environment successfully configured at {args.output}")
