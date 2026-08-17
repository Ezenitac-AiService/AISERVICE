@echo off
setlocal enabledelayedexpansion

echo ======================================================================
echo           AISERVICE Unified Platform Orchestrator (Windows)
echo ======================================================================
echo.

if not exist .env (
    if exist .env.example (
        echo [INFO] .env file not found. Creating from .env.example...
        copy .env.example .env >nul
    ) else (
        echo [WARN] Neither .env nor .env.example found.
    )
)

set ACTION=%1
if "%ACTION%"=="" set ACTION=up

if "%ACTION%"=="up" (
    echo [START] Starting all 10 containers in unified aiservice-network...
    docker compose up -d
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to start containers.
        exit /b %errorlevel%
    )
    echo [K8S] Applying Kubernetes Ingress & gateway-svc...
    kubectl apply -f ddns/ingress-ezenitac.yaml >nul 2>&1
    echo.
    echo ======================================================================
    echo  [SUCCESS] All 10 services are running!
    echo ======================================================================
    echo  - Public HTTPS Portal:    https://ezenitac.duckdns.org/
    echo  - Local Portal Landing:   http://localhost:8080/ (or http://localhost:80/)
    echo  - B-Team Oliview:         https://ezenitac.duckdns.org/bteam/oliview
    echo  - B-Team OllyChat (A):    https://ezenitac.duckdns.org/bteam/chata
    echo  - B-Team OlwonChat (B):   https://ezenitac.duckdns.org/bteam/chatb
    echo  - A-Team Pilos Dashboard: https://ezenitac.duckdns.org/ateam/pilos
    echo  - A-Team Pipeline Worker: Background Scheduled Daemon (pilos-worker)
    echo ======================================================================
) else if "%ACTION%"=="build" (
    echo [BUILD] Rebuilding and starting all 10 containers...
    docker compose up -d --build
    kubectl apply -f ddns/ingress-ezenitac.yaml >nul 2>&1
) else if "%ACTION%"=="down" (
    echo [STOP] Stopping and removing all containers...
    docker compose down
) else if "%ACTION%"=="logs" (
    docker compose logs -f
) else if "%ACTION%"=="status" (
    docker compose ps
    kubectl get ingress,svc -n default
) else if "%ACTION%"=="trigger-worker" (
    echo [TRIGGER] Running A-Team Pipeline manually inside pilos-worker...
    docker exec -it pilos-worker python -m pilos.jobs.run_service_pipeline
) else (
    echo Unknown command: %ACTION%
    echo Usage: %0 [up^|build^|down^|logs^|status^|trigger-worker]
)

endlocal
