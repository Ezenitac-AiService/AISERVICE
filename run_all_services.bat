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
    echo [START] Starting all 9 containers in unified aiservice-network...
    docker compose up -d
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to start containers.
        exit /b %errorlevel%
    )
    echo.
    echo ======================================================================
    echo  [SUCCESS] All services are running!
    echo ======================================================================
    echo  - Unified Portal Landing: http://localhost:8080/
    echo  - B-Team Oliview:         http://localhost:8080/bteam/oliview
    echo  - B-Team OllyChat (A):    http://localhost:8080/bteam/chata
    echo  - B-Team OlwonChat (B):   http://localhost:8080/bteam/chatb
    echo  - A-Team Pilos Dashboard: http://localhost:8080/ateam/pilos
    echo ======================================================================
) else if "%ACTION%"=="build" (
    echo [BUILD] Rebuilding and starting all containers...
    docker compose up -d --build
) else if "%ACTION%"=="down" (
    echo [STOP] Stopping and removing all containers...
    docker compose down
) else if "%ACTION%"=="logs" (
    docker compose logs -f
) else if "%ACTION%"=="status" (
    docker compose ps
) else (
    echo Unknown command: %ACTION%
    echo Usage: %0 [up^|build^|down^|logs^|status]
)

endlocal
