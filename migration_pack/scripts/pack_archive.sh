#!/usr/bin/env bash
# ==============================================================================
# AISERVICE Single Archive Packager Wrapper (Linux / WSL2)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${SCRIPT_DIR}/pack_archive.py" "$@"
