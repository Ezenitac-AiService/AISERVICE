#!/usr/bin/env bash
# ==============================================================================
# vllm_serv: NVIDIA Driver & CUDA Toolkit Automatic Updater (update_cuda_drivers.sh)
# FR-008: OS 패키지 관리자 기반 드라이버/CUDA/cuDNN 최적 패키지 원스톱 갱신 헬퍼
# ==============================================================================

set -eo pipefail

COLOR_GREEN='\033[0;32m'
COLOR_YELLOW='\033[1;33m'
COLOR_RED='\033[0;31m'
COLOR_CYAN='\033[0;36m'
COLOR_NC='\033[0m'

log_info() { echo -e "${COLOR_GREEN}[CUDA UPDATE INFO]${COLOR_NC} $1"; }
log_warn() { echo -e "${COLOR_YELLOW}[CUDA UPDATE WARN]${COLOR_NC} $1"; }
log_err()  { echo -e "${COLOR_RED}[CUDA UPDATE ERROR]${COLOR_NC} $1"; }
log_step() { echo -e "\n${COLOR_CYAN}====================================================${COLOR_NC}\n${COLOR_CYAN}▶ $1${COLOR_NC}\n${COLOR_CYAN}====================================================${COLOR_NC}"; }

if [ "$EUID" -ne 0 ]; then
    log_info "root 권한 확보 시도 중 (sudo 필요)..."
    if ! sudo -v 2>/dev/null; then
        log_err "ERROR: sudo 관리자 권한 승인에 실패하였습니다. 'sudo $0' 명령으로 직접 실행하세요."
        exit 1
    fi
    EXEC_PREFIX="sudo"
else
    EXEC_PREFIX=""
fi

log_step "1. OS 및 NVIDIA 패키지 관리자 환경 감지"

OS_ID="unknown"
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID="$ID"
fi

log_info "감지된 운영체제 ID: $OS_ID ($PRETTY_NAME)"

log_step "2. NVIDIA GPU 드라이버 및 CUDA Toolkit 패키지 최신화 구동"

if command -v apt-get &>/dev/null; then
    log_info "Ubuntu/Debian apt 패키지 매니저 가동 중..."
    $EXEC_PREFIX apt-get update -y || log_warn "apt-get update 중 일부 경고 발생"
    log_info "NVIDIA 드라이버 및 CUDA Toolkit 설치/업데이트 중..."
    $EXEC_PREFIX apt-get install -y --no-install-recommends nvidia-cuda-toolkit nvidia-driver-535 nvidia-utils-535 2>/dev/null || \
    $EXEC_PREFIX apt-get install -y nvidia-cuda-toolkit || true
elif command -v dnf &>/dev/null; then
    log_info "RHEL/Rocky/CentOS dnf 패키지 매니저 가동 중..."
    $EXEC_PREFIX dnf check-update || true
    $EXEC_PREFIX dnf install -y nvidia-driver cuda-toolkit || true
else
    log_warn "지원되는 표준 패키지 매니저(apt/dnf)를 감지하지 못했습니다."
    log_warn "https://developer.nvidia.com/cuda-downloads 에서 수동 업데이트를 진행하세요."
fi

log_step "3. 업데이트 결과 검증"

if command -v nvcc &>/dev/null; then
    log_info "✓ nvcc 설치/업데이트 상태: $(nvcc --version | grep release | head -n 1)"
else
    log_warn "⚠️ nvcc가 감지되지 않았습니다. 환경 변수 PATH에 /usr/local/cuda/bin 이 포함되었는지 확인하세요."
fi

if command -v nvidia-smi &>/dev/null; then
    log_info "✓ nvidia-smi 드라이버 상태: $(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -n 1)"
else
    log_warn "⚠️ nvidia-smi를 찾을 수 없습니다. 시스템 재부팅이 필요할 수 있습니다."
fi

log_info "NVIDIA 드라이버 및 CUDA Toolkit 업데이트 파이프라인 수행 완료."
