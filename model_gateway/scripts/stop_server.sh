#!/usr/bin/env bash
# ==============================================================================
# vllm_serv: 서빙 서버 안전 종료 및 VRAM 해제 스크립트 (stop_server.sh)
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
    BASE_DIR="$SCRIPT_DIR"
elif [ -f "$SCRIPT_DIR/../pyproject.toml" ]; then
    BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
else
    BASE_DIR="$(pwd)"
fi
cd "$BASE_DIR"

PID_FILE="$BASE_DIR/vllm_serv.pid"
DASHBOARD_PID_FILE="$BASE_DIR/vllm_dashboard.pid"

COLOR_GREEN='\033[0;32m'
COLOR_YELLOW='\033[1;33m'
COLOR_RED='\033[0;31m'
COLOR_CYAN='\033[0;36m'
COLOR_NC='\033[0m'

stop_pid() {
    local target_pid=$1
    if [ -n "$target_pid" ] && ps -p "$target_pid" > /dev/null 2>&1; then
        echo -e "${COLOR_CYAN}[STOP] vllm_serv 프로세스(PID: $target_pid) 종료 시도 중 (SIGTERM)...${COLOR_NC}"
        kill "$target_pid" 2>/dev/null || true
        for i in {1..10}; do
            if ! ps -p "$target_pid" > /dev/null 2>&1; then
                echo -e "${COLOR_GREEN}✓ 프로세스 $target_pid 정상 종료 완료.${COLOR_NC}"
                return 0
            fi
            sleep 0.5
        done
        echo -e "${COLOR_YELLOW}[STOP] 강제 종료 수행 (SIGKILL)...${COLOR_NC}"
        kill -9 "$target_pid" 2>/dev/null || true
    fi
}

if [ -f "$PID_FILE" ]; then
    SAVED_PID=$(cat "$PID_FILE")
    stop_pid "$SAVED_PID"
    rm -f "$PID_FILE"
fi

if [ -f "$DASHBOARD_PID_FILE" ]; then
    SAVED_DASH_PID=$(cat "$DASHBOARD_PID_FILE")
    stop_pid "$SAVED_DASH_PID"
    rm -f "$DASHBOARD_PID_FILE"
fi

SERVER_PIDS=$(pgrep -f "src.api.server" || true)
if [ -n "$SERVER_PIDS" ]; then
    for pid in $SERVER_PIDS; do
        stop_pid "$pid"
    done
fi

DASH_PIDS=$(pgrep -f "uvicorn src.api.main:app" || true)
if [ -n "$DASH_PIDS" ]; then
    for pid in $DASH_PIDS; do
        stop_pid "$pid"
    done
fi

# llama-server 잔여 프로세스 추가 정리
LLAMA_PIDS=$(pgrep -f "llama-server" || true)
if [ -n "$LLAMA_PIDS" ]; then
    echo -e "${COLOR_CYAN}[STOP] 잔여 llama-server 하위 프로세스 정리 중: $LLAMA_PIDS${COLOR_NC}"
    for pid in $LLAMA_PIDS; do
        kill -9 "$pid" 2>/dev/null || true
    done
fi

rm -f "$PID_FILE" "$DASHBOARD_PID_FILE" 2>/dev/null || true

if command -v nvidia-smi &> /dev/null; then
    echo -e "${COLOR_GREEN}✓ VRAM 해제 상태 확인:${COLOR_NC}"
    nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
fi

echo -e "${COLOR_GREEN}✓ vllm_serv 서버 및 대시보드 프로세스 종료 완료.${COLOR_NC}"

