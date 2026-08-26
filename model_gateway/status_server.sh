#!/usr/bin/env bash
# ==============================================================================
# vllm_serv: 서빙 및 GPU VRAM 상태 확인 스크립트 (status_server.sh)
# ==============================================================================

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

echo -e "${COLOR_CYAN}====================================================${COLOR_NC}"
echo -e "${COLOR_CYAN} ⚡ vllm_serv 서버 및 멀티 플랫폼 하드웨어 리포트${COLOR_NC}"
echo -e "${COLOR_CYAN}====================================================${COLOR_NC}"

# 멀티 플랫폼 CPU / GPU 하드웨어 및 프로필 실시간 감지 리포트
uv run python -m src.core.cpu_detector --report 2>/dev/null || true

echo -e "\n[서버 프로세스 및 서비스 상태]"

PID=""
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
fi

if [ -z "$PID" ] || ! ps -p "$PID" > /dev/null 2>&1; then
    PID=$(pgrep -f "src.api.server" | tail -n 1 || echo "")
fi

if [ -n "$PID" ] && ps -p "$PID" > /dev/null 2>&1; then
    echo -e "8081 메인 서버 프로세스: ${COLOR_GREEN}🟢 구동 중 (RUNNING, PID: $PID)${COLOR_NC}"
else
    echo -e "8081 메인 서버 프로세스: ${COLOR_YELLOW}⚪ 중지됨 (UNLOADED)${COLOR_NC}"
fi

DASH_PID=""
if [ -f "$DASHBOARD_PID_FILE" ]; then
    DASH_PID=$(cat "$DASHBOARD_PID_FILE")
fi
if [ -z "$DASH_PID" ] || ! ps -p "$DASH_PID" > /dev/null 2>&1; then
    DASH_PID=$(pgrep -f "uvicorn src.api.main:app" | tail -n 1 || echo "")
fi

if [ -n "$DASH_PID" ] && ps -p "$DASH_PID" > /dev/null 2>&1; then
    echo -e "8082 대시보드 프로세스  : ${COLOR_GREEN}🟢 구동 중 (RUNNING, PID: $DASH_PID)${COLOR_NC}"
else
    echo -e "8082 대시보드 프로세스  : ${COLOR_YELLOW}⚪ 중지됨 (UNLOADED)${COLOR_NC}"
fi

SERVER_HOST=$(uv run python -c "from src.core.config_manager import ConfigManager; print(ConfigManager().get_server_config().get('host', '127.0.0.1'))" 2>/dev/null || echo "127.0.0.1")
SERVER_PORT=$(uv run python -c "from src.core.config_manager import ConfigManager; print(ConfigManager().get_server_config().get('port', 8081))" 2>/dev/null || echo "8081")

LAN_IP=$(uv run python -c "from src.core.network_detector import NetworkDetector; print(NetworkDetector.get_active_lan_ips()[-1] if NetworkDetector.get_active_lan_ips() else '127.0.0.1')" 2>/dev/null || echo "127.0.0.1")

PROBE_HOSTS=("127.0.0.1" "localhost" "$LAN_IP")
if [ "$SERVER_HOST" != "0.0.0.0" ] && [ "$SERVER_HOST" != "127.0.0.1" ]; then
    PROBE_HOSTS+=("$SERVER_HOST")
fi

echo -e "\n[REST API 헬스체크 (http://${PROBE_HOSTS[0]}:$SERVER_PORT/health)]"
API_OK=0
if command -v curl &> /dev/null; then
    for host in "${PROBE_HOSTS[@]}"; do
        RESP=$(curl -sL --max-time 3 "http://$host:$SERVER_PORT/health" 2>/dev/null || echo "")
        if [ -n "$RESP" ] && echo "$RESP" | grep -q "status"; then
            echo "$RESP" | python3 -m json.tool 2>/dev/null || echo "$RESP"
            API_OK=1
            break
        fi
    done
fi
if [ "$API_OK" -eq 0 ]; then
    echo -e "${COLOR_YELLOW}응답 없음 (서버 미구현 또는 비활성)${COLOR_NC}"
fi

echo -e "\n[웹 대시보드 헬스체크 (http://${PROBE_HOSTS[0]}:8082/)]"
DASH_OK=0
if command -v curl &> /dev/null; then
    for host in "${PROBE_HOSTS[@]}"; do
        DASH_HTML=$(curl -sL --max-time 3 "http://$host:8082/" 2>/dev/null || echo "")
        if [ -z "$DASH_HTML" ]; then
            DASH_HTML=$(curl -sL --max-time 3 "http://$host:8082/dashboard/" 2>/dev/null || echo "")
        fi
        if echo "$DASH_HTML" | grep -qE "vLLM|Dashboard|vllm_serv|대시보드|LLM|Antigravity|Serving"; then
            echo -e "${COLOR_GREEN}🟢 대시보드 서비스 및 HTML DOM 정상 작동 중 (Port 8082 OPEN, DOM Verified)${COLOR_NC}"
            DASH_OK=1
            break
        elif [ -n "$DASH_HTML" ]; then
            echo -e "${COLOR_YELLOW}⚠️ 대시보드 포트 응답 수신되나 HTML DOM 키워드 검증 미달 (Port 8082 OPEN, Keyword Missing)${COLOR_NC}"
            DASH_OK=1
            break
        fi
    done
fi

if [ "$DASH_OK" -eq 0 ]; then
    SOCKET_BOUND=0
    if command -v lsof &>/dev/null && lsof -i:8082 &>/dev/null; then
        SOCKET_BOUND=1
    elif command -v ss &>/dev/null && ss -tulpn | grep -q ":8082"; then
        SOCKET_BOUND=1
    fi

    if [ "$SOCKET_BOUND" -eq 1 ]; then
        echo -e "${COLOR_GREEN}🟢 대시보드 포트 소켓 개방 확인 (Port 8082 OPEN)${COLOR_NC}"
    else
        echo -e "${COLOR_YELLOW}⚪ 대시보드 미구동 또는 포트 차단됨 (Port 8082 CLOSED)${COLOR_NC}"
    fi
fi


if command -v nvidia-smi &> /dev/null; then
    echo -e "\n[NVIDIA GPU VRAM 실시간 현황]"
    nvidia-smi --query-gpu=name,memory.used,memory.total,temperature.gpu --format=csv,noheader

    # T012: GPU 컴퓨트 프로세스 PID 리스트
    echo -e "\n[GPU 컴퓨트 프로세스 목록]"
    GPU_PROCS=$(nvidia-smi --query-compute-apps=pid,used_memory,name --format=csv,noheader 2>/dev/null)
    if [ -n "$GPU_PROCS" ]; then
        echo -e "PID, VRAM(MiB), Process"
        echo "$GPU_PROCS"
    else
        echo -e "${COLOR_YELLOW}GPU 컴퓨트 프로세스 없음${COLOR_NC}"
    fi
fi

# T012: llama-cpp-python CUDA 빌드 상태
echo -e "\n[CUDA 빌드 상태]"
if command -v nvcc &> /dev/null; then
    echo -e "nvcc: ${COLOR_GREEN}✓ $(nvcc --version 2>/dev/null | grep release | head -n 1)${COLOR_NC}"
else
    echo -e "nvcc: ${COLOR_RED}✗ 미감지${COLOR_NC}"
fi

CUDA_STATUS=$(uv run python -c "
import llama_cpp
fn = getattr(llama_cpp, 'llama_supports_gpu_offload', None) or getattr(llama_cpp, 'llama_supports_gpu', None)
print('True' if fn and fn() else 'False')
" 2>/dev/null || echo "Error")

if [ "$CUDA_STATUS" = "True" ]; then
    echo -e "llama-cpp-python GPU: ${COLOR_GREEN}✓ CUDA 가속 활성${COLOR_NC}"
else
    echo -e "llama-cpp-python GPU: ${COLOR_RED}✗ CPU 전용 모드${COLOR_NC}"
fi
