@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python was not found in PATH.
    pause
    exit /b 1
)

python -c "import chess, numpy, onnxruntime" >nul 2>nul
if errorlevel 1 (
    echo [setup] Installing Value Debugger dependencies...
    python -m pip install python-chess numpy onnxruntime
    if errorlevel 1 (
        echo ERROR: Could not install Value Debugger dependencies.
        pause
        exit /b 1
    )
)

set "PYTHONPATH=%CD%\python;%PYTHONPATH%"
python -m gui.value_debugger_app
if errorlevel 1 (
    echo.
    echo Value Debugger exited with an error.
    pause
    exit /b 1
)
