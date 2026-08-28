#!/usr/bin/env bash
# ==============================================================================
# bootstrap_restore.sh
# ==============================================================================
# AISERVICE Target Host One-Click Bootstrap & Restore Entrypoint v2.0
# Target Platform: Ubuntu Linux 22.04 / 24.04 LTS
# Target Hardware: Intel Core i7-930 (Non-AVX) / GTX 1070 8GB (sm_61) / 24GB RAM
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACK_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ROOT_DIR="$(cd "${PACK_DIR}/.." && pwd)"

# 만약 ROOT_DIR에 docker-compose.yml이 없으면 PACK_DIR을 ROOT_DIR로 설정 (압축 해제 구조 대응)
if [[ ! -f "${ROOT_DIR}/docker-compose.yml" ]] && [[ -f "${PACK_DIR}/docker-compose.yml" ]]; then
    ROOT_DIR="${PACK_DIR}"
fi

log_info() {
    echo -e "\033[1;32m[INFO]\033[0m $*"
}

log_warn() {
    echo -e "\033[1;33m[WARN]\033[0m $*"
}

log_error() {
    echo -e "\033[1;31m[ERROR]\033[0m $*" >&2
}

# 1. 인자 파싱
NON_INTERACTIVE=false
DRY_RUN=false
SKIP_GPU=false
SKIP_DDNS=false
FORCE_DUMP=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        -y|--yes)
            NON_INTERACTIVE=true
            shift
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        --skip-gpu)
            SKIP_GPU=true
            shift
            ;;
        --skip-ddns)
            SKIP_DDNS=true
            shift
            ;;
        --force-dump)
            FORCE_DUMP=true
            shift
            ;;
        -h|--help)
            echo "Usage: sudo ./bootstrap_restore.sh [-y|--yes] [-d|--dry-run] [--skip-gpu] [--skip-ddns] [--force-dump]"
            exit 0
            ;;
        *)
            log_warn "Unknown argument: $1"
            shift
            ;;
    esac
done

log_info "================================================================"
log_info " 🚀 AISERVICE UBUNTU SERVER ONE-CLICK BOOTSTRAP v2.0"
log_info " Root Directory: ${ROOT_DIR}"
log_info " Non-Interactive: ${NON_INTERACTIVE}"
log_info " Dry Run: ${DRY_RUN}"
log_info "================================================================"

# 2. 권한 및 줄바꿈(CRLF -> LF) 정규화
log_info "[Stage 1/7] Normalizing Permissions and File Formats..."
find "${ROOT_DIR}" -type f -name "*.sh" -exec chmod +x {} + 2>/dev/null || true
find "${ROOT_DIR}" -type f -name "*.py" -exec chmod +x {} + 2>/dev/null || true

# 실사용 .env 보안 권한 (chmod 600)
if [[ -f "${ROOT_DIR}/.env" ]]; then
    chmod 600 "${ROOT_DIR}/.env"
    log_info "✓ Applied chmod 600 security permission to '${ROOT_DIR}/.env'."
fi

# 3. 사전 인프라 점검 및 프로비저닝 (Docker Engine & NVIDIA Toolkit)
log_info "[Stage 2/7] Checking Infrastructure Prerequisites..."
if ! command -v docker &>/dev/null || ! docker compose version &>/dev/null; then
    log_info "Docker Engine or Compose plugin not detected. Running automated provisioner..."
    if [[ -f "${SCRIPT_DIR}/install_prerequisites.sh" ]]; then
        bash "${SCRIPT_DIR}/install_prerequisites.sh"
    fi
fi

# 4. Compose WSL2 경로 제거 및 Native Linux GPU 디바이스 정규화
log_info "[Stage 3/7] Normalizing Docker Compose Configuration for Linux..."
if [[ -f "${SCRIPT_DIR}/normalize_compose.py" ]]; then
    python3 "${SCRIPT_DIR}/normalize_compose.py" --input "${ROOT_DIR}/docker-compose.yml"
    log_info "✓ docker-compose.yml normalized for Native Ubuntu GPU runtime."
fi

if [[ "${DRY_RUN}" == "true" ]]; then
    log_info "[DRY-RUN] Pre-checks complete. Halting as requested."
    exit 0
fi

# 5. Model Gateway 하드웨어 자동 감지 및 llama.cpp JIT 컴파일
log_info "[Stage 4/7] Probing Target Hardware & JIT Building Model Gateway..."
if [[ -f "${ROOT_DIR}/model_gateway/scripts/build_llama.sh" ]]; then
    bash "${ROOT_DIR}/model_gateway/scripts/build_llama.sh"
fi

# 6. Docker 볼륨 및 Mutex 데이터베이스 복원 실행
log_info "[Stage 5/7] Restoring Docker Volumes and Databases (Mutex Pipeline)..."
RESTORE_PY_ARGS=()
if [[ "${FORCE_DUMP}" == "true" ]]; then
    RESTORE_PY_ARGS+=("--force-dump")
fi
if [[ "${NON_INTERACTIVE}" == "true" ]]; then
    RESTORE_PY_ARGS+=("--force")
fi

python3 "${SCRIPT_DIR}/bootstrap_restore.py" "${RESTORE_PY_ARGS[@]}"

# 7. DuckDNS 동적 DNS IPv4 즉시 갱신 및 5분 주기 크론 등록
if [[ "${SKIP_DDNS}" == "false" ]] && [[ -f "${ROOT_DIR}/ddns/duck.sh" ]]; then
    log_info "[Stage 6/7] Synchronizing DuckDNS Dynamic DNS & Scheduling Cron..."
    bash "${ROOT_DIR}/ddns/duck.sh" || log_warn "DuckDNS initial update call failed, continuing..."

    # Crontab 5분 주기 등록 (중복 방지 멱등 등록)
    CRON_CMD="*/5 * * * * ${ROOT_DIR}/ddns/duck.sh >/dev/null 2>&1"
    (crontab -l 2>/dev/null | grep -v "duck.sh" || true; echo "${CRON_CMD}") | crontab -
    log_info "✓ DuckDNS 5-minute update cronjob registered in host crontab."
fi

# 8. Readiness Probe 대기 및 E2E 11개 엔드포인트 무결성 검증
log_info "[Stage 7/7] Running 11-Endpoint Verification Gate..."
log_info "Waiting 10s for application container stabilization..."
sleep 10

if [[ -f "${SCRIPT_DIR}/verify_migration.py" ]]; then
    python3 "${SCRIPT_DIR}/verify_migration.py" || {
        log_warn "Some endpoints failed initial check. Polling for final health (up to 30s)..."
        sleep 15
        python3 "${SCRIPT_DIR}/verify_migration.py"
    }
fi

log_info "================================================================"
log_info " 🎉 AISERVICE UBUNTU SERVER MIGRATION & BOOTSTRAP: 100% COMPLETE"
log_info "================================================================"
