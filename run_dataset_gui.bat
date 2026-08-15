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

python -c "import chess, chess.engine" >nul 2>nul
if errorlevel 1 (
    echo [setup] python-chess is missing. Installing it for this Python...
    python -m pip install python-chess
    if errorlevel 1 (
        echo ERROR: Could not install python-chess automatically.
        pause
        exit /b 1
    )
)

set "PYTHONPATH=%CD%\python;%PYTHONPATH%"
python -m gui.dataset_app
if errorlevel 1 (
    echo.
    echo Dataset GUI exited with an error.
    pause
    exit /b 1
)
