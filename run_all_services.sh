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
    echo "[START] Starting all 10 containers in unified aiservice-network..."
    docker compose up -d
    echo "[K8S] Applying Kubernetes Ingress & gateway-svc..."
    kubectl apply -f ddns/ingress-ezenitac.yaml >/dev/null 2>&1 || true
    echo ""
    echo "======================================================================"
    echo " [SUCCESS] All 10 services are running!"
    echo "======================================================================"
    echo " - Public HTTPS Portal:    https://ezenitac.duckdns.org/"
    echo " - Local Portal Landing:   http://localhost:8080/ (or http://localhost:80/)"
    echo " - B-Team Oliview:         https://ezenitac.duckdns.org/bteam/oliview"
    echo " - B-Team OllyChat (A):    https://ezenitac.duckdns.org/bteam/chata"
    echo " - B-Team OlwonChat (B):   https://ezenitac.duckdns.org/bteam/chatb"
    echo " - A-Team Pilos Dashboard: https://ezenitac.duckdns.org/ateam/pilos"
    echo " - A-Team Pipeline Worker: Background Scheduled Daemon (pilos-worker)"
    echo "======================================================================"
elif [ "$ACTION" = "build" ]; then
    echo "[BUILD] Rebuilding and starting all 10 containers..."
    docker compose up -d --build
    kubectl apply -f ddns/ingress-ezenitac.yaml >/dev/null 2>&1 || true
elif [ "$ACTION" = "down" ]; then
    echo "[STOP] Stopping and removing all containers..."
    docker compose down
elif [ "$ACTION" = "logs" ]; then
    docker compose logs -f
elif [ "$ACTION" = "status" ]; then
    docker compose ps
    kubectl get ingress,svc -n default || true
elif [ "$ACTION" = "trigger-worker" ]; then
    echo "[TRIGGER] Running A-Team Pipeline manually inside pilos-worker..."
    docker exec -it pilos-worker python -m pilos.jobs.run_service_pipeline
else
    echo "Unknown command: $ACTION"
    echo "Usage: $0 [up|build|down|logs|status|trigger-worker]"
fi
