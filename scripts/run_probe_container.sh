#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Run One-Shot Probe Container (T047)
# ==============================================================================
# Executes aiservice-probe within Docker aiservice-network to verify 9 endpoints.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AISERVICE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

REPORT_FILE="${1:-${AISERVICE_DIR}/migration_pack/verification_report.json}"

echo "[INFO] Running one-shot aiservice-probe container..."
docker compose -f "${AISERVICE_DIR}/docker-compose.yml" run --rm aiservice-probe /bin/sh -c "/app/scripts/probe_endpoints.sh /tmp/report.json && cat /tmp/report.json" > "${REPORT_FILE}"

echo "[SUCCESS] Probe results written to ${REPORT_FILE}"
