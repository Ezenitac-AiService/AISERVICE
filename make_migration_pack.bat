@echo off
REM ==============================================================================
REM AISERVICE Master Migration Pack Generator (Windows One-Click Wrapper)
REM ==============================================================================
setlocal enabledelayedexpansion

set PROJECT_ROOT=%~dp0

echo [AISERVICE] Starting Master Migration Pack Builder...

where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    python "%PROJECT_ROOT%make_migration_pack.py" %*
    exit /b %ERRORLEVEL%
)

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    py -3 "%PROJECT_ROOT%make_migration_pack.py" %*
    exit /b %ERRORLEVEL%
)

if exist "%USERPROFILE%\.local\bin\python3.12.exe" (
    "%USERPROFILE%\.local\bin\python3.12.exe" "%PROJECT_ROOT%make_migration_pack.py" %*
    exit /b %ERRORLEVEL%
)

echo [ERROR] Python 3 not found in PATH.
exit /b 1
