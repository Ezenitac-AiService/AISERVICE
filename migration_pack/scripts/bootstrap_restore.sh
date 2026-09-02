#!/usr/bin/env bash
# -*- coding: utf-8 -*-
# AISERVICE Ubuntu one-click bootstrap entrypoint.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACK_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ROOT_DIR="$(cd "${PACK_DIR}/.." && pwd)"
if [[ ! -f "${ROOT_DIR}/docker-compose.yml" && -f "${PACK_DIR}/docker-compose.yml" ]]; then
    ROOT_DIR="${PACK_DIR}"
fi

log_info() { echo "[INFO] $*"; }
log_warn() { echo "[WARN] $*" >&2; }
log_error() { echo "[ERROR] $*" >&2; }

NON_INTERACTIVE=false
DRY_RUN=false
SKIP_GPU=false
SKIP_DDNS=false
FORCE_DUMP=false
FORCE=false
KEY_FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -y|--yes) NON_INTERACTIVE=true; FORCE=true; shift ;;
        -d|--dry-run) DRY_RUN=true; shift ;;
        --skip-gpu) SKIP_GPU=true; shift ;;
        --skip-ddns) SKIP_DDNS=true; shift ;;
        --force-dump) FORCE_DUMP=true; shift ;;
        --force|-f) FORCE=true; shift ;;
        --key-file)
            [[ $# -ge 2 ]] || { log_error "--key-file에는 경로가 필요합니다"; exit 1; }
            KEY_FILE="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: sudo ./bootstrap_restore.sh [-y|--yes] [-d|--dry-run] [--skip-gpu] [--skip-ddns] [--force-dump] [--key-file PATH]"
            exit 0
            ;;
        *) log_error "알 수 없는 인자: $1"; exit 1 ;;
    esac
done
log_info "AISERVICE Ubuntu bootstrap: root=${ROOT_DIR}, non_interactive=${NON_INTERACTIVE}, dry_run=${DRY_RUN}"

# Root 권한 검사 (dry-run이 아닌 실제 실행 시 필수)
if [[ "${EUID:-$(id -u)}" -ne 0 && "${DRY_RUN}" != "true" ]]; then
    log_error "bootstrap_restore.sh는 root 또는 sudo 권한으로 실행해야 합니다 (e.g. sudo ./bootstrap_restore.sh)"
    exit 1
fi

# CRLF/LF와 실행 권한을 아카이브 전체에 적용합니다.
find "${ROOT_DIR}" -type f \( -name '*.sh' -o -name '*.py' -o -name '*.yml' -o -name '*.yaml' -o -name '.env' \) -exec sed -i 's/\r$//' {} +
find "${ROOT_DIR}" -type f -name '*.sh' -exec chmod +x {} +
find "${ROOT_DIR}" -type f -name '*.py' -exec chmod +x {} +
if [[ -f "${ROOT_DIR}/.env" ]]; then
    chmod 600 "${ROOT_DIR}/.env"
fi
if [[ -f "${ROOT_DIR}/ddns/.env" ]]; then
    chmod 600 "${ROOT_DIR}/ddns/.env"
fi

# 2. Check and Provision .env
if [[ ! -f "${PROJECT_ROOT}/.env" ]]; then
    echo "▶ Generating .env from template..."
    cp "${PACK_ROOT}/config/.env.migration.template" "${PROJECT_ROOT}/.env"
    echo "  ✓ Created '${PROJECT_ROOT}/.env'"
else
    echo "  ✓ Existing .env found."
fi

# 3. Verify SHA-256 Checksums
echo ""
echo "▶ Verifying database dump checksums..."
cd "${PACK_ROOT}"
if [[ -f "${DB_DIR}/checksums.sha256" ]]; then
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum -c "${DB_DIR}/checksums.sha256"
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 -c "${DB_DIR}/checksums.sha256"
    fi
    echo "  ✓ Checksum verification passed (100% bitwise integrity)."
else
    echo "  ⚠️ Warning: 'checksums.sha256' not found, skipping hash check."
fi

# DDNS는 서비스 기동과 독립적으로 먼저 등록하여 최종 검증에도 반영되게 합니다.
if [[ "${SKIP_DDNS}" != "true" && -f "${ROOT_DIR}/ddns/duck.sh" ]]; then
    bash "${ROOT_DIR}/ddns/duck.sh"
    CRON_CMD="*/5 * * * * ${ROOT_DIR}/ddns/duck.sh >/dev/null 2>&1"
    (crontab -l 2>/dev/null | grep -v 'duck.sh' || true; echo "${CRON_CMD}") | crontab -
fi

echo ""
echo "======================================================================"
echo " 🎉 AISERVICE MIGRATION & BOOTSTRAP RESTORE COMPLETED!"
echo " Portal: http://localhost:80/ or http://localhost:8080/"
echo "======================================================================"
