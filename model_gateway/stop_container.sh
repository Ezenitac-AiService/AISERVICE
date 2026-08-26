#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=============================================================================="
echo "[STOP] vLLM Serv: Stopping Container Daemon"
echo "=============================================================================="

docker compose down

echo "[INFO] vLLM Serv Container stopped cleanly."
