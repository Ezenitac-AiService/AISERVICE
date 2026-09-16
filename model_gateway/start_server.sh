#!/usr/bin/env bash
# ==============================================================================
# vllm_serv: 백그라운드 데몬 서버 구동 스크립트 (start_server.sh)
# Port 8081 메인 API 서버 (Dual-LLM: 9B 32K + 4B 8K) 단일 데몬 구동 및 90초 Readiness 검증
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
chmod 0644 "$BASE_DIR"/config/*.json 2>/dev/null || true

PID_FILE="$BASE_DIR/vllm_serv.pid"
LOG_FILE="$BASE_DIR/logs/server.log"

COLOR_GREEN='\033[0;32m'
COLOR_YELLOW='\033[1;33m'
COLOR_RED='\033[0;31m'
COLOR_CYAN='\033[0;36m'
COLOR_NC='\033[0m'

# Conflict check without || true masking
if pgrep -f "src.api.server" > /dev/null 2>&1; then
    SERVER_RUNNING=$(pgrep -f "src.api.server")
    echo -e "${COLOR_YELLOW}[SERVER WARN] 이미 구동 중인 서버 프로세스가 감지되었습니다.${COLOR_NC}"
    echo -e "  - 8081 메인 서버 PID: $SERVER_RUNNING"
    echo -e "${COLOR_YELLOW}기존 프로세스를 먼저 종료하려면 './stop_server.sh' 명령을 실행한 후 다시 시도하세요.${COLOR_NC}"
    exit 1
fi

echo -e "${COLOR_CYAN}[SERVER] Model Gateway Dual-LLM 서빙 데몬 구동 파이프라인을 시작합니다...${COLOR_NC}"
echo -e "${COLOR_CYAN}[SERVER] 하드웨어 가속 사전 점검(Pre-flight check) 수행 중...${COLOR_NC}"
if ! uv run python -m src.core.cpu_detector --check-preflight; then
    echo -e "${COLOR_RED}[SERVER ERROR] 사전 하드웨어 점검 실패! 백그라운드 서버 데몬을 구동하지 않고 즉시 종료합니다.${COLOR_NC}"
    echo -e "${COLOR_YELLOW}해결 가이드: NVIDIA GPU 드라이버(nvidia-smi) 및 CUDA Compiler(nvcc) 환경을 확인하세요.${COLOR_NC}"
    exit 1
fi
echo -e "${COLOR_GREEN}[SERVER] ✓ 하드웨어 가속 사전 점검 완료 (GPU CUDA 가속 활성)${COLOR_NC}"

echo -e "${COLOR_GREEN}[SERVER] 1. llama-server 바이너리 빌드 상태 및 모델 가중치 사전 배치 확인${COLOR_NC}"
echo -e "${COLOR_GREEN}[SERVER] 2. Dual-LLM (9B Port 8089 + 4B Port 8088) VRAM 100% 오프로드 검증 수행${COLOR_NC}"
echo -e "${COLOR_GREEN}[SERVER] 3. 8081 메인 로그: $LOG_FILE${COLOR_NC}"

mkdir -p "$BASE_DIR/logs"

# 8081 메인 API 서버 단일 데몬 백그라운드 가동 (uv run 기반)
nohup setsid uv run python -m src.api.server < /dev/null > "$LOG_FILE" 2>&1 &
SERVER_PID=$!

sleep 0.5
if pgrep -f "src.api.server" > /dev/null 2>&1; then
    ACTUAL_SERVER_PID=$(pgrep -f "src.api.server" | tail -n 1)
else
    ACTUAL_SERVER_PID="$SERVER_PID"
fi

echo "$ACTUAL_SERVER_PID" > "$PID_FILE"
echo -e "${COLOR_GREEN}✓ 서버 데몬 백그라운드 구동 시작! (8081 PID: $ACTUAL_SERVER_PID)${COLOR_NC}"

SERVER_HOST=$(uv run python -c "from src.core.config_manager import ConfigManager; print(ConfigManager().get_server_config().get('host', '127.0.0.1'))" 2>/dev/null || echo "127.0.0.1")
SERVER_PORT=$(uv run python -c "from src.core.config_manager import ConfigManager; print(ConfigManager().get_server_config().get('port', 8081))" 2>/dev/null || echo "8081")

CURL_HOST="$SERVER_HOST"
if [ "$CURL_HOST" = "0.0.0.0" ]; then
    CURL_HOST="127.0.0.1"
fi

# 8081 Readiness 검증 대기 (최대 90초)
echo -n "[SERVER] 8081 메인 서버 READY 상태 대기 중 (최대 90초)..."
READY=0
for i in {1..90}; do
    if curl -s "http://$CURL_HOST:$SERVER_PORT/health/readiness" | grep -q '"status":"ready"' 2>/dev/null || \
       curl -s "http://$CURL_HOST:$SERVER_PORT/health" > /dev/null 2>&1 || \
       curl -s "http://$CURL_HOST:$SERVER_PORT/v1/models" > /dev/null 2>&1; then
        READY=1
        break
    fi
    echo -n "."
    sleep 1
done

if [ "$READY" -eq 1 ]; then
    echo -e "\n${COLOR_GREEN}✓ 8081 메인 인퍼런스 서버 가동 완료!${COLOR_NC}"
    echo -e "OpenAI API 엔드포인트: http://$SERVER_HOST:$SERVER_PORT/v1/chat/completions"
    echo -e "웹 대시보드 URL: http://$SERVER_HOST:$SERVER_PORT/dashboard/"
    exit 0
else
    echo -e "\n${COLOR_RED}[SERVER ERROR] 90초 이내 8081 Readiness 검증 실패! 원자적 롤백(Clean Exit)을 수행합니다.${COLOR_NC}"
    echo -e "${COLOR_RED}최근 서버 로그 출력 (tail -n 15):${COLOR_NC}"
    tail -n 15 "$LOG_FILE" 2>/dev/null || true
    if [ -n "$ACTUAL_SERVER_PID" ]; then
        kill -9 "$ACTUAL_SERVER_PID" 2>/dev/null || true
    fi
    pkill -f "src.api.server" 2>/dev/null || true
    rm -f "$PID_FILE"
    exit 1
fi
