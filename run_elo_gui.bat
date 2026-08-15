@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python was not found in PATH.
    echo Install Python 3 and enable "Add Python to PATH".
    pause
    exit /b 1
)

set "PYTHONPATH=%CD%\python;%PYTHONPATH%"
python -m gui.benchmark_app
if errorlevel 1 (
    echo.
    echo Benchmark GUI exited with an error.
    pause
    exit /b 1
)
