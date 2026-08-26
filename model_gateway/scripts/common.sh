#!/usr/bin/env bash
# ==============================================================================
# vllm_serv: 공통 쉘 믹스인 스크립트 (scripts/common.sh)
# (090-audit-test-refactor)
# ==============================================================================

COLOR_GREEN='\033[0;32m'
COLOR_YELLOW='\033[1;33m'
COLOR_RED='\033[0;31m'
COLOR_CYAN='\033[0;36m'
COLOR_NC='\033[0m'

log_info() { echo -e "${COLOR_GREEN}[$(date +'%H:%M:%S') INFO]${COLOR_NC} $1"; }
log_warn() { echo -e "${COLOR_YELLOW}[$(date +'%H:%M:%S') WARN]${COLOR_NC} $1"; }
log_err()  { echo -e "${COLOR_RED}[$(date +'%H:%M:%S') ERROR]${COLOR_NC} $1" >&2; }
log_step() { echo -e "\n${COLOR_CYAN}====================================================${COLOR_NC}\n${COLOR_CYAN}▶ $1${COLOR_NC}\n${COLOR_CYAN}====================================================${COLOR_NC}"; }

check_cuda_gpu_available() {
    if command -v nvidia-smi &>/dev/null && nvidia-smi -L &>/dev/null; then
        return 0
    elif [ -e /dev/nvidia0 ] || [ -d /proc/driver/nvidia ]; then
        return 0
    else
        return 1
    fi
}

get_nvidia_driver_version() {
    if command -v nvidia-smi &>/dev/null; then
        nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n 1
    elif [ -f /proc/driver/nvidia/version ]; then
        grep -oP 'NVIDIA Module\s+\K[0-9.]+' /proc/driver/nvidia/version 2>/dev/null || echo "Unknown"
    else
        echo "None"
    fi
}

get_cuda_version() {
    if command -v nvcc &>/dev/null; then
        nvcc --version 2>/dev/null | grep -oP 'release \K[0-9.]+' | head -n 1
    elif command -v nvidia-smi &>/dev/null; then
        nvidia-smi 2>/dev/null | grep -oP 'CUDA Version:\s*\K[0-9.]+' | head -n 1
    else
        echo "None"
    fi
}

get_cudnn_version() {
    local header=""
    for p in /usr/include/cudnn_version.h /usr/local/cuda/include/cudnn_version.h /usr/include/cudnn.h; do
        if [ -f "$p" ]; then
            header="$p"
            break
        fi
    done

    if [ -n "$header" ]; then
        local major=$(grep -i '#define CUDNN_MAJOR' "$header" 2>/dev/null | awk '{print $3}')
        local minor=$(grep -i '#define CUDNN_MINOR' "$header" 2>/dev/null | awk '{print $3}')
        local patch=$(grep -i '#define CUDNN_PATCHLEVEL' "$header" 2>/dev/null | awk '{print $3}')
        if [ -n "$major" ] && [ -n "$minor" ] && [ -n "$patch" ]; then
            echo "${major}.${minor}.${patch}"
            return 0
        fi
    fi
    echo "Unknown"
}

assert_cuda_gpu() {
    if ! check_cuda_gpu_available; then
        log_err "NVIDIA CUDA GPU가 장착되지 않거나 드라이버가 인식되지 않는 환경입니다."
        log_err "본 프로젝트는 CUDA GPU 전용 플랫폼 호스트만을 지원합니다. (090-audit-test-refactor)"
        exit 1
    fi
    log_info "✓ NVIDIA CUDA GPU 환경 탐지 성공 (Driver: $(get_nvidia_driver_version), CUDA: $(get_cuda_version))"
}

# -----------------------------------------------------------------------------
# FR-007 / T003: SRE 안전 래퍼 함수 (옵셔널 예외 폭사 방지)
# -----------------------------------------------------------------------------
try_optional_step() {
    local step_name="$1"
    shift
    log_info "옵셔널 파이프라인 단계 시도: $step_name ($*)"
    if "$@"; then
        log_info "✓ [$step_name] 옵셔널 단계 정상 완수"
        return 0
    else
        local status=$?
        log_warn "⚠️ [$step_name] 옵셔널 단계 경고 수신 (Exit Code: $status). non-fatal 안전 처리하고 계속 진행합니다."
        return 0
    fi
}

# -----------------------------------------------------------------------------
# FR-008 / T004: DevSecOps Cascade 포트 결정 믹스인
# Priority: CLI argument > Environment variable > config/server_config.json > Default
# -----------------------------------------------------------------------------
get_configured_port() {
    local port_type="${1:-main}"
    local default_port=8081
    local env_val=""

    case "$port_type" in
        main)
            default_port=8081
            env_val="${LLAMA_PORT:-}"
            ;;
        dashboard)
            default_port=8082
            env_val="${DASHBOARD_PORT:-}"
            ;;
        embedding)
            default_port=8090
            env_val="${EMBEDDING_PORT:-}"
            ;;
        rerank)
            default_port=8091
            env_val="${RERANK_PORT:-}"
            ;;
        *)
            default_port=8081
            ;;
    esac

    if [ -n "$env_val" ]; then
        echo "$env_val"
        return 0
    fi

    local base_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    local cfg_file="$base_dir/config/server_config.json"
    if [ -f "$cfg_file" ] && command -v python3 &>/dev/null; then
        local cfg_port=$(python3 -c "import json; c=json.load(open('$cfg_file')); print(c.get('$port_type', c.get('port', $default_port)))" 2>/dev/null || echo "$default_port")
        echo "$cfg_port"
        return 0
    fi

    echo "$default_port"
}

# -----------------------------------------------------------------------------
# FR-001 ~ FR-006 / T003 & T007: 3대 멀티 플랫폼 HW 차등 감지 믹스인
# -----------------------------------------------------------------------------
detect_hardware_profile() {
    local base_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    if command -v python3 &>/dev/null; then
        PYTHONPATH="$base_dir" python3 -c "from src.core.cpu_detector import get_hardware_profile_capability; print(get_hardware_profile_capability().platform_type)" 2>/dev/null || echo "UNKNOWN_GENERIC"
    else
        echo "UNKNOWN_GENERIC"
    fi
}

get_hardware_cmake_args() {
    local base_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    if command -v python3 &>/dev/null; then
        PYTHONPATH="$base_dir" python3 -m src.core.cpu_detector --format cmake 2>/dev/null || echo "-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86"
    else
        echo "-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86"
    fi
}

log_hardware_capability_report() {
    local base_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    if command -v python3 &>/dev/null; then
        PYTHONPATH="$base_dir" python3 -m src.core.cpu_detector --report
    else
        log_warn "python3 미장착으로 상세 하드웨어 감지 리포트를 건너땁니다."
    fi
}


