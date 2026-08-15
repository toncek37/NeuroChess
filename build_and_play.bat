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

rem CMake needs a real C++ toolchain. A normal Command Prompt does not
rem automatically expose MSVC even when Visual Studio Build Tools are installed.
where cl >nul 2>nul
if errorlevel 1 (
    set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
    if exist "%VSWHERE%" (
        for /f "usebackq tokens=*" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSINSTALL=%%i"
    )

    if defined VSINSTALL if exist "%VSINSTALL%\Common7\Tools\VsDevCmd.bat" (
        echo Activating Visual Studio C++ build environment...
        call "%VSINSTALL%\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 >nul
    )
)

where cl >nul 2>nul
if errorlevel 1 (
    echo.
    echo ERROR: No Microsoft C++ compiler was found.
    echo.
    echo Install "Visual Studio 2022 Build Tools" and select the workload:
    echo   Desktop development with C++
    echo.
    echo Required components include MSVC x64/x86 build tools and a Windows SDK.
    echo After installation, run this file again; no manual Developer Prompt is needed.
    goto :fail
)

where nmake >nul 2>nul
if errorlevel 1 (
    echo ERROR: MSVC was found, but nmake.exe is unavailable.
    echo Repair/install the "Desktop development with C++" workload.
    goto :fail
)

echo Compiler detected:
cl 2>&1 | findstr /c:"Compiler Version"
echo.

echo [1/3] Configuring CMake...
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
if errorlevel 1 (
    echo.
    echo ERROR: CMake configuration failed.
    echo If this build directory was created with a different generator, delete the
    echo "build" folder once and run this launcher again.
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
