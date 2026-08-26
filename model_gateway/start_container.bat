@echo off
setlocal enabledelayedexpansion

echo ==============================================================================
echo [START] vLLM Serv: Windows 11 LLM Container Launcher
echo ==============================================================================

:: Check Docker CLI & Engine
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker daemon or Rancher Desktop is not running!
    echo Please start Rancher Desktop or Docker Desktop and try again.
    pause
    exit /b 1
)

:: Ensure volume directories exist
if not exist "models" mkdir models
if not exist "config" mkdir config
if not exist "data" mkdir data

echo [INFO] Building and starting vLLM Serv Container with GPU Passthrough...
docker compose up -d --build

if %errorlevel% equ 0 (
    echo.
    echo ==============================================================================
    echo [SUCCESS] vLLM Serv Container is running in background!
    echo.
    echo   - Web Dashboard UI:  http://127.0.0.1:8081/dashboard/ (or :8000)
    echo   - OpenAI API:        http://127.0.0.1:8081/v1/chat/completions
    echo   - Health Check:      http://127.0.0.1:8081/health
    echo   - Embedding API:     http://127.0.0.1:8090/v1/embeddings
    echo   - Reranker API:      http://127.0.0.1:8091/v1/rerank
    echo.
    echo Stop container anytime with: stop_container.bat
    echo ==============================================================================
) else (
    echo [ERROR] Failed to start container via docker compose.
)

endlocal
