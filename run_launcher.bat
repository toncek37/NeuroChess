@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where pythonw >nul 2>nul
if errorlevel 1 (
    where python >nul 2>nul
    if errorlevel 1 (
        echo ERROR: Python was not found in PATH.
        echo Install Python 3 and enable "Add Python to PATH".
        pause
        exit /b 1
    )
    start "" /b python -m gui.launcher_app
    exit /b 0
)

set "PYTHONPATH=%CD%\python;%PYTHONPATH%"
start "" pythonw -m gui.launcher_app
exit /b 0
