#!/usr/bin/env bash
# ==============================================================================
# install_prerequisites.sh
# ==============================================================================
# Clean Ubuntu 22.04 / 24.04 LTS Automated Infrastructure Provisioner
# - Official APT Docker Engine & Compose plugin (Snap Docker excluded)
# - NVIDIA Driver & NVIDIA Container Toolkit v1.16+ configuration
# - Python 3, Build essentials, CMake for JIT compilation
# ==============================================================================
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
DPKG_OPTS=(-o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold")
ASSUME_YES="${AISERVICE_ASSUME_YES:-0}"

log_info() {
    echo -e "\033[1;32m[INFO]\033[0m $*"
}

log_warn() {
    echo -e "\033[1;33m[WARN]\033[0m $*"
}

log_error() {
    echo -e "\033[1;31m[ERROR]\033[0m $*" >&2
}

# 1. Root 권한 검사
if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root or with sudo."
    exit 1
fi

TARGET_USER="${SUDO_USER:-$USER}"

log_info "================================================================"
log_info "AISERVICE Ubuntu 24.04 LTS Infrastructure Auto-Provisioner"
log_info "Target User: ${TARGET_USER}"
log_info "Non-interactive install: ${ASSUME_YES}"
log_info "================================================================"

# 2. Snap Docker 감지 및 경고/제거 가드레일 (Snap Docker는 GPU 접근을 차단함)
if command -v snap &>/dev/null && snap list 2>/dev/null | grep -q -E '^docker '; then
    log_warn "Detected Snap-packaged Docker! Snap sandboxing blocks GPU access (/dev/nvidia*)."
    log_warn "Removing Snap Docker and replacing with official APT Docker repository..."
    snap remove docker || true
fi

# 3. 기본 빌드 도구 및 필수 패키지 설치
log_info "[1/4] Installing system baseline utilities & build toolchain..."
apt-get update -qq
apt-get install -y "${DPKG_OPTS[@]}" \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    build-essential \
    cmake \
    git \
    python3 \
    python3-pip \
    python-is-python3 \
    tar \
    gzip \
    pciutils \
    cron \
    ubuntu-drivers-common

# 4. 공식 Docker Engine & Docker Compose 플러그인 설치
if ! command -v docker &>/dev/null || ! docker compose version &>/dev/null; then
    log_info "[2/4] Setting up official Docker APT repository..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    UBUNTU_CODENAME="$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")"
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
      ${UBUNTU_CODENAME} stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -qq
    apt-get install -y "${DPKG_OPTS[@]}" \
        docker-ce \
        docker-ce-cli \
        containerd.io \
        docker-buildx-plugin \
        docker-compose-plugin

    log_info "Docker Engine $(docker --version) installed successfully."
else
    log_info "[2/4] Docker Engine is already installed: $(docker --version)"
fi

# 사용자 docker 그룹 등록
if [[ -n "${TARGET_USER}" ]] && id "${TARGET_USER}" &>/dev/null; then
    usermod -aG docker "${TARGET_USER}" || true
    log_info "Added user '${TARGET_USER}' to 'docker' group."
fi

# 5. NVIDIA GPU 하드웨어 감지 및 NVIDIA Container Toolkit 설치
log_info "[3/4] Checking for NVIDIA GPU Hardware..."
HAS_NVIDIA_GPU=false
if [[ "${AISERVICE_SKIP_GPU:-0}" != "1" ]] && lspci 2>/dev/null | grep -i nvidia &>/dev/null; then
    HAS_NVIDIA_GPU=true
    GPU_NAME="$(lspci 2>/dev/null | grep -i nvidia | head -n1)"
    log_info "NVIDIA GPU hardware detected: ${GPU_NAME}"
fi

if [[ "${HAS_NVIDIA_GPU}" == "true" ]]; then
    # NVIDIA 드라이버 존재 확인
    if ! command -v nvidia-smi &>/dev/null; then
        log_warn "NVIDIA driver not found. Installing recommended headless server driver..."
        command -v ubuntu-drivers >/dev/null 2>&1 || {
            log_error "ubuntu-drivers가 설치되지 않았습니다."
            exit 2
        }
        ubuntu-drivers install --gpgpu || ubuntu-drivers install
    fi

    # NVIDIA Container Toolkit 설치
    if ! dpkg -s nvidia-container-toolkit &>/dev/null; then
        log_info "Installing NVIDIA Container Toolkit v1.16+..."
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
        curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
          sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
          tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null

        apt-get update -qq
        apt-get install -y "${DPKG_OPTS[@]}" nvidia-container-toolkit
    fi

    log_info "Configuring Docker runtime for NVIDIA Container Toolkit..."
    nvidia-ctk runtime configure --runtime=docker
    systemctl restart docker
    docker info >/dev/null 2>&1 || {
        log_error "NVIDIA runtime 구성 후 Docker daemon 검증에 실패했습니다."
        exit 2
    }
    log_info "Docker NVIDIA GPU runtime successfully configured and restarted."
else
    log_info "No NVIDIA GPU hardware detected. System configured for high-performance CPU serving."
    systemctl restart docker || true
fi

# 6. 최종 인프라 검증
log_info "[4/4] Verifying Docker environment..."
docker info >/dev/null 2>&1 || {
    log_error "Docker daemon is not running!"
    exit 1
}

log_info "================================================================"
log_info "Prerequisites Installation & Verification: COMPLETED SUCCESSFULLY"
log_info "================================================================"
