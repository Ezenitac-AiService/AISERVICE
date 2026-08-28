#!/usr/bin/env bash
# ==============================================================================
# duck.sh - DuckDNS IPv4 Dynamic DNS Updater for Ubuntu Linux
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_FILE="${SCRIPT_DIR}/duckdns.log"

log() {
    local msg="$1"
    local ts
    ts="$(date '+%Y-%m-%d %H:%M:%S %z')"
    echo "[${ts}] ${msg}" >> "${LOG_FILE}"
}

# 1. 환경 변수 탐색 (.env -> ddns/.env -> 시스템 env)
DOMAIN="${DUCKDNS_DOMAIN:-}"
TOKEN="${DUCKDNS_TOKEN:-}"

if [[ -z "${TOKEN}" ]] && [[ -f "${SCRIPT_DIR}/.env" ]]; then
    TOKEN="$(grep -E '^token=' "${SCRIPT_DIR}/.env" | cut -d'=' -f2- | tr -d '\r"' || true)"
    if [[ -z "${DOMAIN}" ]]; then
        DOMAIN="$(grep -E '^domain=' "${SCRIPT_DIR}/.env" | cut -d'=' -f2- | tr -d '\r"' || true)"
    fi
fi

if [[ -z "${TOKEN}" ]] && [[ -f "${ROOT_DIR}/.env" ]]; then
    TOKEN="$(grep -E '^DUCKDNS_TOKEN=' "${ROOT_DIR}/.env" | cut -d'=' -f2- | tr -d '\r"' || true)"
    if [[ -z "${DOMAIN}" ]]; then
        DOMAIN="$(grep -E '^DUCKDNS_DOMAIN=' "${ROOT_DIR}/.env" | cut -d'=' -f2- | tr -d '\r"' || true)"
    fi
fi

DOMAIN="${DOMAIN:-ezenitac}"

if [[ -z "${TOKEN}" ]]; then
    log "ERROR: DuckDNS token is empty. Please configure DUCKDNS_TOKEN in .env or ddns/.env"
    echo "ERROR: DuckDNS token is empty." >&2
    exit 1
fi

# 2. DuckDNS IPv4 강제(-4) 갱신 API 호출
UPDATE_URL="https://www.duckdns.org/update?domains=${DOMAIN}&token=${TOKEN}&ip="

RESPONSE="$(curl -4 --silent --show-error --max-time 30 --retry 3 --retry-delay 2 "${UPDATE_URL}" 2>&1 || true)"
RESPONSE_TRIMMED="$(echo "${RESPONSE}" | tr -d '\r\n ')"

if [[ "${RESPONSE_TRIMMED}" == "OK" ]]; then
    log "SUCCESS: DuckDNS update OK for domain(s) '${DOMAIN}'"
    echo "DuckDNS update OK: ${DOMAIN}"
    exit 0
else
    log "ERROR: DuckDNS update failed for '${DOMAIN}'. Response: ${RESPONSE}"
    echo "ERROR: DuckDNS update failed: ${RESPONSE}" >&2
    exit 1
fi
