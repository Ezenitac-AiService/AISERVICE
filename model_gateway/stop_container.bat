@echo off
setlocal

echo ==============================================================================
echo [STOP] vLLM Serv: Stopping Container Daemon
echo ==============================================================================

docker compose down

echo [INFO] vLLM Serv Container stopped cleanly.
endlocal
