#!/usr/bin/env bash
set -e

echo "======================================================================"
echo "          AISERVICE Unified Platform Orchestrator (Linux/macOS)       "
echo "======================================================================"
echo ""

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "[INFO] .env file not found. Creating from .env.example..."
        cp .env.example .env
    else
        echo "[WARN] Neither .env nor .env.example found."
    fi
fi

ACTION="${1:-up}"

case "$ACTION" in
    up)
        echo "[START] Starting all 9 containers in unified aiservice-network..."
        docker compose up -d
        echo ""
        echo "======================================================================"
        echo " [SUCCESS] All services are running!"
        echo "======================================================================"
        echo " - Unified Portal Landing: http://localhost:8080/"
        echo " - B-Team Oliview:         http://localhost:8080/bteam/oliview"
        echo " - B-Team OllyChat (A):    http://localhost:8080/bteam/chata"
        echo " - B-Team OlwonChat (B):   http://localhost:8080/bteam/chatb"
        echo " - A-Team Pilos Dashboard: http://localhost:8080/ateam/pilos"
        echo "======================================================================"
        ;;
    build)
        echo "[BUILD] Rebuilding and starting all containers..."
        docker compose up -d --build
        ;;
    down)
        echo "[STOP] Stopping and removing all containers..."
        docker compose down
        ;;
    logs)
        docker compose logs -f
        ;;
    status)
        docker compose ps
        ;;
    *)
        echo "Unknown command: $ACTION"
        echo "Usage: $0 [up|build|down|logs|status]"
        exit 1
        ;;
esac
