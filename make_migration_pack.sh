#!/usr/bin/env bash
# ==============================================================================
# AISERVICE Master Migration Pack Generator (Linux / macOS / WSL2 One-Click Wrapper)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${SCRIPT_DIR}/make_migration_pack.py" "$@"
