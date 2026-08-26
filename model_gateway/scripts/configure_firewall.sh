#!/usr/bin/env bash
# ==============================================================================
# vllm_serv: 멀티 OS 방화벽 포트 개방 헬퍼 스크립트 (configure_firewall.sh)
# ==============================================================================
# 039-seed-pack-sudo-firewall-migration (FR-003, FR-004, DoD-002, DoD-003)
#
# 사용법:
#   sudo ./scripts/configure_firewall.sh [PORTS...]
#
# 기본 포트:
#   8081/tcp (대시보드/OpenAI API), 8089/tcp (백엔드 llama.cpp)
#
# 지원 방화벽:
#   ufw, firewalld, nftables, iptables
# ==============================================================================

set -eo pipefail

COLOR_GREEN='\033[0;32m'
COLOR_YELLOW='\033[1;33m'
COLOR_RED='\033[0;31m'
COLOR_CYAN='\033[0;36m'
COLOR_NC='\033[0m'

log_info() { echo -e "${COLOR_GREEN}[FIREWALL INFO]${COLOR_NC} $1"; }
log_warn() { echo -e "${COLOR_YELLOW}[FIREWALL WARN]${COLOR_NC} $1"; }
log_err()  { echo -e "${COLOR_RED}[FIREWALL ERROR]${COLOR_NC} $1"; }

# ------------------------------------------------------------------------------
# Root 권한 검증
# ------------------------------------------------------------------------------
if [ "$EUID" -ne 0 ]; then
    log_err "이 스크립트는 root 권한이 필요합니다."
    log_err "사용법: sudo $0 [PORTS...]"
    exit 1
fi

# ------------------------------------------------------------------------------
# 대상 포트 파싱 (기본값: 8081 8089 8090 8091)
# ------------------------------------------------------------------------------
if [ $# -gt 0 ]; then
    TARGET_PORTS=("$@")
else
    TARGET_PORTS=(8081 8089 8090 8091)
fi

# ------------------------------------------------------------------------------
# OS 방화벽 백엔드 감지
# ------------------------------------------------------------------------------
detect_firewall_system() {
    if command -v ufw &> /dev/null; then
        UFW_STATUS=$(ufw status 2>/dev/null | head -n 1 || true)
        if echo "$UFW_STATUS" | grep -qi "active"; then
            echo "ufw"
            return
        fi
    fi
    if command -v firewall-cmd &> /dev/null; then
        FWD_STATE=$(firewall-cmd --state 2>/dev/null || true)
        if [ "$FWD_STATE" = "running" ]; then
            echo "firewalld"
            return
        fi
    fi
    if command -v nft &> /dev/null; then
        if nft list ruleset &> /dev/null; then
            echo "nftables"
            return
        fi
    fi
    if command -v iptables &> /dev/null; then
        echo "iptables"
        return
    fi
    echo "unknown"
}

# ------------------------------------------------------------------------------
# 방화벽별 포트 개방 함수
# ------------------------------------------------------------------------------
allow_port_ufw() {
    local port=$1
    log_info "ufw: 포트 ${port}/tcp 허용 규칙 등록 중..."
    ufw allow "${port}/tcp"
    log_info "✓ ufw allow ${port}/tcp 완료"
}

allow_port_firewalld() {
    local port=$1
    log_info "firewalld: 포트 ${port}/tcp 영구 허용 규칙 등록 중..."
    firewall-cmd --permanent --add-port="${port}/tcp"
    log_info "✓ firewall-cmd --permanent --add-port=${port}/tcp 완료"
}

allow_port_nftables() {
    local port=$1
    log_info "nftables: 포트 ${port}/tcp 허용 규칙 등록 중..."
    nft add rule inet filter input tcp dport "${port}" accept 2>/dev/null || \
        nft add rule ip filter INPUT tcp dport "${port}" accept 2>/dev/null || \
        log_warn "nftables 테이블/체인 구조가 상이합니다. 수동 추가가 필요할 수 있습니다."
    log_info "✓ nftables 포트 ${port}/tcp 규칙 추가 시도 완료"
}

allow_port_iptables() {
    local port=$1
    log_info "iptables: 포트 ${port}/tcp 허용 규칙 등록 중..."
    iptables -C INPUT -p tcp --dport "${port}" -j ACCEPT 2>/dev/null || \
        iptables -A INPUT -p tcp --dport "${port}" -j ACCEPT
    log_info "✓ iptables 포트 ${port}/tcp 규칙 등록 완료"
}

# ------------------------------------------------------------------------------
# 메인 실행
# ------------------------------------------------------------------------------
FW_SYSTEM=$(detect_firewall_system)
log_info "감지된 OS 방화벽 시스템: ${FW_SYSTEM}"

case "$FW_SYSTEM" in
    ufw)
        for port in "${TARGET_PORTS[@]}"; do
            allow_port_ufw "$port"
        done
        log_info "ufw 상태 요약:"
        ufw status verbose
        ;;
    firewalld)
        for port in "${TARGET_PORTS[@]}"; do
            allow_port_firewalld "$port"
        done
        firewall-cmd --reload
        log_info "firewalld 리로드 완료. 현재 열린 포트:"
        firewall-cmd --list-ports
        ;;
    nftables)
        for port in "${TARGET_PORTS[@]}"; do
            allow_port_nftables "$port"
        done
        log_info "nftables 룰셋 적용 완료."
        ;;
    iptables)
        for port in "${TARGET_PORTS[@]}"; do
            allow_port_iptables "$port"
        done
        log_info "iptables 현재 INPUT 체인 상태:"
        iptables -L INPUT -n --line-numbers 2>/dev/null || true
        ;;
    unknown)
        log_warn "활성화된 OS 방화벽을 감지하지 못했습니다."
        log_warn "방화벽이 비활성화 상태이거나 미설치 환경입니다."
        log_warn "포트 접근에 문제가 있으면 수동으로 방화벽 규칙을 확인하세요."
        ;;
esac

log_info "방화벽 포트 구성 완료: ${TARGET_PORTS[*]}"
exit 0
