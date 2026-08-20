@echo off
REM ==============================================================================
REM AISERVICE Target Host One-Click Bootstrap & Restore Wrapper (Windows)
REM ==============================================================================
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set PACK_ROOT=%SCRIPT_DIR%..

echo [AISERVICE] Starting One-Click Bootstrap & Restore...

where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    python "%SCRIPT_DIR%bootstrap_restore.py" %*
    exit /b %ERRORLEVEL%
)

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    py -3 "%SCRIPT_DIR%bootstrap_restore.py" %*
    exit /b %ERRORLEVEL%
)

if exist "%USERPROFILE%\.local\bin\python3.12.exe" (
    "%USERPROFILE%\.local\bin\python3.12.exe" "%SCRIPT_DIR%bootstrap_restore.py" %*
    exit /b %ERRORLEVEL%
)

echo [ERROR] Python 3 not found in PATH.
exit /b 1
