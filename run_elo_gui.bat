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

rem The Elo GUI/match runner only needs python-chess. Do not install the full
rem training requirements here (notably torch) just to run a benchmark.
python -c "import chess" >nul 2>nul
if errorlevel 1 (
    echo [setup] python-chess is missing. Installing it for this Python...
    python -m pip install python-chess
    if errorlevel 1 (
        echo.
        echo ERROR: Could not install python-chess automatically.
        echo Try: python -m pip install python-chess
        pause
        exit /b 1
    )
    echo [setup] python-chess installed successfully.
    echo.
)

set "PYTHONPATH=%CD%\python;%PYTHONPATH%"
python -m gui.benchmark_app
if errorlevel 1 (
    echo.
    echo Benchmark GUI exited with an error.
    pause
    exit /b 1
)
