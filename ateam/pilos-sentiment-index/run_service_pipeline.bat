@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [PILOS] Python virtual environment was not found: .venv\Scripts\python.exe
    endlocal
    exit /b 1
)

".venv\Scripts\python.exe" -m pilos.jobs.run_service_pipeline %*
set "PILOS_PIPELINE_EXIT_CODE=%ERRORLEVEL%"

endlocal & exit /b %PILOS_PIPELINE_EXIT_CODE%
