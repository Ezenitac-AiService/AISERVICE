@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo   A-Team Container Services Manager
echo ===================================================

:: Check if docker works in Windows, otherwise use wsl docker
docker version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    set DOCKER_CMD=wsl -d Ubuntu -e docker
    set COMPOSE_CMD=wsl -d Ubuntu -e bash -c "cd /mnt/c/AISERVICE/ateam && docker compose
) else (
    set DOCKER_CMD=docker
    set COMPOSE_CMD=docker compose
)

if "%1"=="" goto start
if "%1"=="start" goto start
if "%1"=="stop" goto stop
if "%1"=="restart" goto restart
if "%1"=="logs" goto logs
if "%1"=="status" goto status
if "%1"=="init-db" goto init_db

echo Usage: %0 [start|stop|restart|logs|status|init-db]
goto end

:start
echo [1/3] Initializing network...
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\check_ports.ps1"
wsl -d Ubuntu -e bash -c "cd /mnt/c/AISERVICE/ateam && bash scripts/init_network.sh"
echo [2/3] Starting A-Team containers (Web: 8080, DB: 3307)...
wsl -d Ubuntu -e bash -c "cd /mnt/c/AISERVICE/ateam && docker compose up -d --build"
echo.
echo [SUCCESS] A-Team services started!
echo Web Dashboard: http://localhost:8080
echo Database Port: localhost:3307
goto end

:stop
echo Stopping A-Team containers...
wsl -d Ubuntu -e bash -c "cd /mnt/c/AISERVICE/ateam && docker compose down"
echo [SUCCESS] A-Team services stopped.
goto end

:restart
echo Restarting A-Team containers...
wsl -d Ubuntu -e bash -c "cd /mnt/c/AISERVICE/ateam && docker compose restart"
goto end

:logs
wsl -d Ubuntu -e bash -c "cd /mnt/c/AISERVICE/ateam && docker compose logs -f"
goto end

:status
wsl -d Ubuntu -e bash -c "cd /mnt/c/AISERVICE/ateam && docker compose ps"
goto end

:init_db
echo Starting DB dump restoration (pilos_v2.sql)...
wsl -d Ubuntu -e bash -c "cd /mnt/c/AISERVICE/ateam && bash scripts/import_db_dump.sh"
goto end

:end
endlocal
