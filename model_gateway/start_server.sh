#!/usr/bin/env bash
# ==============================================================================
# vllm_serv: 백그라운드 데몬 서버 구동 스크립트 (start_server.sh)
# llama.cpp C++ 바이너리 자동 빌드 및 모델 자동 다운로드 파이프라인 수행
# Port 8081 메인 API 서버 및 Port 8082 웹 대시보드 동시 Readiness & 원자적 롤백 지원
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
LOG_FILE="$BASE_DIR/logs/server.log"
DASHBOARD_LOG_FILE="$BASE_DIR/logs/dashboard.log"

COLOR_GREEN='\033[0;32m'
COLOR_YELLOW='\033[1;33m'
COLOR_RED='\033[0;31m'
COLOR_CYAN='\033[0;36m'
COLOR_NC='\033[0m'

SERVER_RUNNING=$(pgrep -f "src.api.server" || true)
DASH_RUNNING=$(pgrep -f "uvicorn src.api.main:app" || true)
if [ -n "$SERVER_RUNNING" ] || [ -n "$DASH_RUNNING" ]; then
    echo -e "${COLOR_YELLOW}[SERVER WARN] 이미 구동 중이거나 단독 상주 중인 서버/대시보드 프로세스가 감지되었습니다.${COLOR_NC}"
    [ -n "$SERVER_RUNNING" ] && echo -e "  - 8081 메인 서버 PID: $SERVER_RUNNING"
    [ -n "$DASH_RUNNING" ] && echo -e "  - 8082 대시보드 PID: $DASH_RUNNING"
    echo -e "${COLOR_YELLOW}기존 프로세스를 먼저 종료하려면 './stop_server.sh' 명령을 실행한 후 다시 시도하세요.${COLOR_NC}"
    exit 1
fi


echo -e "${COLOR_CYAN}[SERVER] vllm_serv 인퍼런스 서빙 서버 및 웹 대시보드 구동 파이프라인을 시작합니다...${COLOR_NC}"
echo -e "${COLOR_CYAN}[SERVER] 하드웨어 가속 사전 점검(Pre-flight check) 수행 중...${COLOR_NC}"
if ! uv run python -m src.core.cpu_detector --check-preflight; then
    echo -e "${COLOR_RED}[SERVER ERROR] 사전 하드웨어 점검 실패! 백그라운드 서버 데몬을 구동하지 않고 즉시 종료합니다.${COLOR_NC}"
    echo -e "${COLOR_YELLOW}해결 가이드: NVIDIA GPU 드라이버(nvidia-smi) 및 CUDA Compiler(nvcc) 환경을 확인하세요.${COLOR_NC}"
    exit 1
fi
echo -e "${COLOR_GREEN}[SERVER] ✓ 하드웨어 가속 사전 점검 완료 (GPU CUDA 가속 활성)${COLOR_NC}"

echo -e "${COLOR_GREEN}[SERVER] 1. llama-server 바이너리 빌드 상태 및 모델 가중치 자동 다운로드 파이프라인 가동${COLOR_NC}"
echo -e "${COLOR_GREEN}[SERVER] 2. 기본 VRAM 상주 서빙 모델(qwen3.5-4b) VRAM 100% 오프로드 검증 수행${COLOR_NC}"
echo -e "${COLOR_GREEN}[SERVER] 3. 8081 메인 로그: $LOG_FILE | 8082 대시보드 로그: $DASHBOARD_LOG_FILE${COLOR_NC}"

mkdir -p "$BASE_DIR/logs"

# 8081 메인 API 서버 및 8082 웹 대시보드 데몬 동시 백그라운드 가동 (uv run 기반)
nohup setsid uv run python -m src.api.server < /dev/null > "$LOG_FILE" 2>&1 &
SERVER_PID=$!
nohup setsid uv run python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8082 < /dev/null > "$DASHBOARD_LOG_FILE" 2>&1 &
DASHBOARD_PID=$!

sleep 0.5
ACTUAL_SERVER_PID=$(pgrep -f "src.api.server" | tail -n 1 || echo "$SERVER_PID")
ACTUAL_DASHBOARD_PID=$(pgrep -f "uvicorn src.api.main:app" | tail -n 1 || echo "$DASHBOARD_PID")

echo "$ACTUAL_SERVER_PID" > "$PID_FILE"
echo "$ACTUAL_DASHBOARD_PID" > "$DASHBOARD_PID_FILE"

echo -e "${COLOR_GREEN}✓ 서버 데몬 백그라운드 구동 시작! (8081 PID: $ACTUAL_SERVER_PID, 8082 PID: $ACTUAL_DASHBOARD_PID)${COLOR_NC}"

SERVER_HOST=$(uv run python -c "from src.core.config_manager import ConfigManager; print(ConfigManager().get_server_config().get('host', '127.0.0.1'))" 2>/dev/null || echo "127.0.0.1")
SERVER_PORT=$(uv run python -c "from src.core.config_manager import ConfigManager; print(ConfigManager().get_server_config().get('port', 8081))" 2>/dev/null || echo "8081")

CURL_HOST="$SERVER_HOST"
if [ "$CURL_HOST" = "0.0.0.0" ]; then
    CURL_HOST="127.0.0.1"
fi

# 동시 Readiness 검증 대기 (최대 30초)
echo -n "[SERVER] 8081 메인 서버 및 8082 대시보드 동시 READY 상태 대기 중 (최대 30초)..."
READY=0
for i in {1..30}; do
    P8081_OK=0
    P8082_OK=0
    if curl -s "http://$CURL_HOST:$SERVER_PORT/health" > /dev/null 2>&1 || curl -s "http://$CURL_HOST:$SERVER_PORT/v1/models" > /dev/null 2>&1; then
        P8081_OK=1
    fi
    if curl -s "http://$CURL_HOST:8082/" > /dev/null 2>&1; then
        P8082_OK=1
    fi

    if [ "$P8081_OK" -eq 1 ] && [ "$P8082_OK" -eq 1 ]; then
        READY=1
        break
    fi
    echo -n "."
    sleep 1
done

if [ "$READY" -eq 1 ]; then
    echo -e "\n${COLOR_GREEN}✓ 8081 메인 인퍼런스 서버 및 8082 웹 대시보드 동시 가동 완료!${COLOR_NC}"
    echo -e "OpenAI API 엔드포인트: http://$SERVER_HOST:$SERVER_PORT/v1/chat/completions"
    echo -e "웹 대시보드 URL: http://$SERVER_HOST:8082/"
    exit 0
else
    echo -e "\n${COLOR_RED}[SERVER ERROR] [SERVER DIAGNOSTICS] 30초 이내 8081/8082 동시 Readiness 검증 실패! 원자적 롤백(Clean Exit)을 수행합니다.${COLOR_NC}"
    echo -e "${COLOR_RED}최근 서버 로그 출력 (tail -n 15):${COLOR_NC}"
    tail -n 15 "$LOG_FILE" 2>/dev/null || true
    [ -n "$ACTUAL_SERVER_PID" ] && kill -9 "$ACTUAL_SERVER_PID" 2>/dev/null || true
    [ -n "$ACTUAL_DASHBOARD_PID" ] && kill -9 "$ACTUAL_DASHBOARD_PID" 2>/dev/null || true
    pkill -f "src.api.server" 2>/dev/null || true
    pkill -f "uvicorn src.api.main:app" 2>/dev/null || true
    rm -f "$PID_FILE" "$DASHBOARD_PID_FILE"
    exit 1
fi
