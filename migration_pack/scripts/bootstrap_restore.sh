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

while [[ $# -gt 0 ]]; do
    case "$1" in
        -y|--yes) NON_INTERACTIVE=true; FORCE=true; shift ;;
        -d|--dry-run) DRY_RUN=true; shift ;;
        --skip-gpu) SKIP_GPU=true; shift ;;
        --skip-ddns) SKIP_DDNS=true; shift ;;
        --force-dump) FORCE_DUMP=true; shift ;;
        --force|-f) FORCE=true; shift ;;
        -h|--help)
            echo "Usage: sudo ./bootstrap_restore.sh [-y|--yes] [-d|--dry-run] [--skip-gpu] [--skip-ddns] [--force-dump]"
            exit 0
            ;;
        *) log_error "알 수 없는 인자: $1"; exit 1 ;;
    esac
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

if [[ "${DRY_RUN}" == "true" ]]; then
    python3 "${SCRIPT_DIR}/bootstrap_restore.py" --dry-run
    exit $?
fi

# Docker와 GPU를 독립적으로 검사하도록 provisioner를 항상 호출합니다.
if [[ "${SKIP_GPU}" == "true" ]]; then
    export AISERVICE_SKIP_GPU=1
fi
if [[ "${NON_INTERACTIVE}" == "true" ]]; then
    export AISERVICE_ASSUME_YES=1
fi
bash "${SCRIPT_DIR}/install_prerequisites.sh"

python3 "${SCRIPT_DIR}/normalize_compose.py" --input "${ROOT_DIR}/docker-compose.yml"

if [[ -f "${ROOT_DIR}/model_gateway/scripts/build_llama.sh" && "${SKIP_GPU}" != "true" ]]; then
    bash "${ROOT_DIR}/model_gateway/scripts/build_llama.sh"
fi

# DDNS는 서비스 기동과 독립적으로 먼저 등록하여 최종 검증에도 반영되게 합니다.
if [[ "${SKIP_DDNS}" != "true" && -f "${ROOT_DIR}/ddns/duck.sh" ]]; then
    bash "${ROOT_DIR}/ddns/duck.sh"
    CRON_CMD="*/5 * * * * ${ROOT_DIR}/ddns/duck.sh >/dev/null 2>&1"
    (crontab -l 2>/dev/null | grep -v 'duck.sh' || true; echo "${CRON_CMD}") | crontab -
fi

RESTORE_ARGS=()
if [[ "${FORCE}" == "true" ]]; then
    RESTORE_ARGS+=(--yes)
fi
if [[ "${FORCE_DUMP}" == "true" ]]; then
    RESTORE_ARGS+=(--force-dump)
fi
if [[ "${SKIP_DDNS}" == "true" ]]; then
    RESTORE_ARGS+=(--skip-ddns)
fi
python3 "${SCRIPT_DIR}/bootstrap_restore.py" "${RESTORE_ARGS[@]}"
# bootstrap_restore.py invokes verify_migration.py as the final gate.

log_info "AISERVICE Ubuntu migration bootstrap 완료"
