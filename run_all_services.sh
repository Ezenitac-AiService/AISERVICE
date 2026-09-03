#!/usr/bin/env bash
set -e

echo "======================================================================"
echo "          AISERVICE Unified Platform Orchestrator (Linux/WSL)"
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

if [ "$ACTION" = "up" ]; then
    echo "[START] Starting containers in unified aiservice-network..."
    docker compose up -d
    echo ""
    echo "======================================================================"
    echo " [SUCCESS] AISERVICE containers are running!"
    echo "======================================================================"
    echo " - Portal Landing:         http://localhost:3000/"
    echo " - B-Team Oliview:         http://localhost:8002/ (or /bteam/oliview/)"
    echo " - B-Team OllyChat (A):    http://localhost:8003/ (or /bteam/chata/)"
    echo " - B-Team OlwonChat (B):   http://localhost:8004/ (or /bteam/chatb/)"
    echo " - A-Team Pilos Dashboard: http://localhost:8001/ (or /ateam/pilos/)"
    echo " - A-Team Pipeline Worker: Background Scheduled Daemon (pilos-worker)"
    echo "======================================================================"
elif [ "$ACTION" = "build" ]; then
    echo "[BUILD] Rebuilding and starting containers..."
    docker compose up -d --build
elif [ "$ACTION" = "down" ]; then
    echo "[STOP] Stopping and removing all containers..."
    docker compose down
elif [ "$ACTION" = "logs" ]; then
    docker compose logs -f
elif [ "$ACTION" = "status" ]; then
    docker compose ps
elif [ "$ACTION" = "trigger-worker" ]; then
    echo "[TRIGGER] Running A-Team Pipeline manually inside pilos-worker..."
    docker exec -it pilos-worker python -m pilos.jobs.run_service_pipeline
else
    echo "Unknown command: $ACTION"
    echo "Usage: $0 [up|build|down|logs|status|trigger-worker]"
fi
