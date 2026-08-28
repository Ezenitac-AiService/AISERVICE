#!/usr/bin/env bash
# ==============================================================================
# AISERVICE Root Bootstrap Wrapper
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_SCRIPT="${SCRIPT_DIR}/migration_pack/scripts/bootstrap_restore.sh"

if [[ -f "${TARGET_SCRIPT}" ]]; then
    exec bash "${TARGET_SCRIPT}" "$@"
else
    echo "Error: ${TARGET_SCRIPT} not found!" >&2
    exit 1
fi
