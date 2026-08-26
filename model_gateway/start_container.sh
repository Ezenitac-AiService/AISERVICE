#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=============================================================================="
echo "[START] vLLM Serv: WSL2/Linux Container Launcher"
echo "=============================================================================="

if ! docker info > /dev/null 2>&1; then
    echo "[ERROR] Docker engine is not accessible. Please ensure Docker/Rancher Desktop is running."
    exit 1
fi

mkdir -p models config data

echo "[INFO] Building and starting vLLM Serv Container with GPU Passthrough..."
docker compose up -d --build

echo ""
echo "=============================================================================="
echo "[SUCCESS] vLLM Serv Container is running in background!"
echo ""
echo "  - Web Dashboard UI:  http://127.0.0.1:8081/dashboard/ (or :8000)"
echo "  - OpenAI API:        http://127.0.0.1:8081/v1/chat/completions"
echo "  - Health Check:      http://127.0.0.1:8081/health"
echo "  - Embedding API:     http://127.0.0.1:8090/v1/embeddings"
echo "  - Reranker API:      http://127.0.0.1:8091/v1/rerank"
echo ""
echo "Stop container anytime with: ./stop_container.sh"
echo "=============================================================================="
