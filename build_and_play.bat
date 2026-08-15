@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo   NeuroChess - Build and Play
echo ========================================
echo.

where cmake >nul 2>nul
if errorlevel 1 (
    echo ERROR: CMake was not found in PATH.
    echo Install CMake and enable "Add CMake to PATH" during installation.
    goto :fail
)

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python was not found in PATH.
    echo Install Python 3 and enable "Add Python to PATH" during installation.
    goto :fail
)

echo [1/3] Configuring CMake...
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
if errorlevel 1 (
    echo.
    echo ERROR: CMake configuration failed.
    goto :fail
)

echo.
echo [2/3] Building NeuroChess...
cmake --build build --config Release --parallel
if errorlevel 1 (
    echo.
    echo ERROR: Compilation failed. The compiler output above contains the reason.
    goto :fail
)

set "ENGINE="
if exist "build\Release\neurochess.exe" set "ENGINE=build\Release\neurochess.exe"
if not defined ENGINE if exist "build\neurochess.exe" set "ENGINE=build\neurochess.exe"
if not defined ENGINE if exist "build\Debug\neurochess.exe" set "ENGINE=build\Debug\neurochess.exe"

if not defined ENGINE (
    echo.
    echo ERROR: Build finished, but neurochess.exe was not found.
    echo Searching the build directory:
    where /r build neurochess.exe 2>nul
    goto :fail
)

echo.
echo [3/3] Starting GUI with %ENGINE%...
python play_gui.py --engine "%ENGINE%"
if errorlevel 1 (
    echo.
    echo ERROR: GUI exited with an error.
    goto :fail
)

exit /b 0

:fail
echo.
echo Build/play failed. Press any key to close this window.
pause >nul
exit /b 1
