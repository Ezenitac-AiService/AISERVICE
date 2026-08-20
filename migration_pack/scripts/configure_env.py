#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AISERVICE Environment Profiler & Configuration Synchronizer (configure_env.py)
-------------------------------------------------------------------------------
Generates and validates .env files for target deployment environments based on
the unified .env.migration.template.
"""

import sys
import os
import argparse
from datetime import datetime

# Windows Console UTF-8 safety
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PACK_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(PACK_ROOT, ".."))
TEMPLATE_PATH = os.path.join(PACK_ROOT, "config", ".env.migration.template")

REQUIRED_KEYS = [
    "GATEWAY_PORT",
    "PILOS_DB_NAME",
    "PILOS_DB_USER",
    "PILOS_DB_PASSWORD",
    "BTEAM_DB_NAME",
    "BTEAM_DB_USER",
    "BTEAM_DB_PASSWORD",
    "LLM_BASE_URL",
]


def load_env_file(file_path: str) -> dict[str, str]:
    env_vars = {}
    if not os.path.exists(file_path):
        return env_vars
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                env_vars[key.strip()] = val.strip()
    return env_vars


def configure_environment(output_path: str, overrides: dict[str, str] | None = None) -> bool:
    if not os.path.exists(TEMPLATE_PATH):
        print(f"❌ Error: Template not found at '{TEMPLATE_PATH}'")
        return False

    overrides = overrides or {}
    lines = []

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        for line in f:
            raw_line = line.rstrip("\r\n")
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                lines.append(raw_line)
                continue
            if "=" in stripped:
                key, default_val = stripped.split("=", 1)
                key = key.strip()
                val = overrides.get(key, default_val.strip())
                lines.append(f"{key}={val}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"✓ Environment configuration written to: {output_path}")

    # Validate required keys
    loaded = load_env_file(output_path)
    missing = [k for k in REQUIRED_KEYS if not loaded.get(k)]
    if missing:
        print(f"⚠️ Warning: Missing required keys in generated config: {missing}")
        return False

    print("✓ Configuration validation passed (all required keys present).")
    return True


def main():
    parser = argparse.ArgumentParser(description="AISERVICE Environment Profiler")
    parser.add_argument("--output", type=str, default=os.path.join(PROJECT_ROOT, ".env"), help="Output path for .env file")
    parser.add_argument("--gateway-port", type=str, help="Override GATEWAY_PORT (e.g., 80 or 8080)")
    parser.add_argument("--gateway-alt-port", type=str, help="Override GATEWAY_ALT_PORT")
    parser.add_argument("--pilos-db-pass", type=str, help="Override PILOS_DB_PASSWORD")
    parser.add_argument("--bteam-db-pass", type=str, help="Override BTEAM_DB_PASSWORD")
    args = parser.parse_args()

    overrides = {}
    if args.gateway_port:
        overrides["GATEWAY_PORT"] = args.gateway_port
    if args.gateway_alt_port:
        overrides["GATEWAY_ALT_PORT"] = args.gateway_alt_port
    if args.pilos_db_pass:
        overrides["PILOS_DB_PASSWORD"] = args.pilos_db_pass
    if args.bteam_db_pass:
        overrides["BTEAM_DB_PASSWORD"] = args.bteam_db_pass

    success = configure_environment(args.output, overrides)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
