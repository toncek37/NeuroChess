@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python was not found in PATH.
    pause
    exit /b 1
)

python -c "import torch, onnx" >nul 2>nul
if errorlevel 1 (
    echo [setup] Installing ONNX export dependency...
    python -m pip install onnx
    if errorlevel 1 (
        echo ERROR: Could not install ONNX Python package.
        pause
        exit /b 1
    )
)

set "PYTHONPATH=%CD%\python;%PYTHONPATH%"
python -m gui.neural_setup_app
if errorlevel 1 (
    echo.
    echo Neural setup GUI exited with an error.
    pause
    exit /b 1
)
