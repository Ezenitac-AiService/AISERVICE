#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "============================================================"
echo " Restoring AISERVICE Secrets & DDNS Configuration"
echo "============================================================"

if command -v uv &> /dev/null; then
    uv run --project "$ROOT_DIR/bteam" python "$SCRIPT_DIR/restore_secrets.py" "$@"
elif command -v python3 &> /dev/null; then
    python3 "$SCRIPT_DIR/restore_secrets.py" "$@"
else
    python "$SCRIPT_DIR/restore_secrets.py" "$@"
fi
