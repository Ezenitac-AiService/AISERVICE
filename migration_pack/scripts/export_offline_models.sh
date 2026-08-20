#!/usr/bin/env bash
# ==============================================================================
# AISERVICE Offline Model Exporter Wrapper (Linux / WSL2)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${SCRIPT_DIR}/export_offline_models.py" "$@"
