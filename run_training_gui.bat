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

python -c "import torch, numpy, chess" >nul 2>nul
if errorlevel 1 (
    echo [setup] Training dependencies are missing. Installing torch, numpy and python-chess...
    python -m pip install torch numpy python-chess
    if errorlevel 1 (
        echo.
        echo ERROR: Could not install training dependencies automatically.
        pause
        exit /b 1
    )
    echo [setup] Dependencies installed successfully.
    echo.
)

set "PYTHONPATH=%CD%\python;%PYTHONPATH%"
python -m gui.training_app
if errorlevel 1 (
    echo.
    echo Training GUI exited with an error.
    pause
    exit /b 1
)
