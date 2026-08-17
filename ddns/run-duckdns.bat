@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%Update-DuckDns.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo DuckDNS update failed. Check "%SCRIPT_DIR%duckdns.log".
)

exit /b %EXIT_CODE%
