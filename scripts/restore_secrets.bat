@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "ROOT_DIR=%SCRIPT_DIR%.."

echo ============================================================
echo  Restoring AISERVICE Secrets ^& DDNS Configuration
echo ============================================================

where uv >nul 2>&1
if %errorlevel% equ 0 (
    uv run --project "%ROOT_DIR%\bteam" python "%SCRIPT_DIR%restore_secrets.py" %*
) else (
    python "%SCRIPT_DIR%restore_secrets.py" %*
)
