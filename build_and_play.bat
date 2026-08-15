@echo off
setlocal EnableExtensions EnableDelayedExpansion
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

rem A normal Command Prompt does not expose MSVC automatically.
where cl >nul 2>nul
if errorlevel 1 (
    set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
    if exist "!VSWHERE!" (
        for /f "tokens=*" %%i in ('"!VSWHERE!" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath') do set "VSINSTALL=%%i"
    )

    if defined VSINSTALL (
        echo Found Visual Studio at: !VSINSTALL!
        if exist "!VSINSTALL!\VC\Auxiliary\Build\vcvars64.bat" (
            echo Activating MSVC x64 environment via vcvars64.bat...
            call "!VSINSTALL!\VC\Auxiliary\Build\vcvars64.bat"
        ) else if exist "!VSINSTALL!\Common7\Tools\VsDevCmd.bat" (
            echo Activating Visual Studio C++ build environment via VsDevCmd.bat...
            call "!VSINSTALL!\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64
        )
    )
)

where cl >nul 2>nul
if errorlevel 1 (
    echo.
    echo ERROR: Visual Studio with C++ tools was detected, but cl.exe is still unavailable.
    echo.
    if defined VSINSTALL echo Detected installation: !VSINSTALL!
    echo Expected one of these setup scripts:
    if defined VSINSTALL echo   !VSINSTALL!\VC\Auxiliary\Build\vcvars64.bat
    if defined VSINSTALL echo   !VSINSTALL!\Common7\Tools\VsDevCmd.bat
    echo.
    echo Open Visual Studio Installer - Modify and verify:
    echo   Desktop development with C++
    echo   MSVC v143 x64/x86 build tools
    echo   Windows 10/11 SDK
    goto :fail
)

where nmake >nul 2>nul
if errorlevel 1 (
    echo ERROR: MSVC was activated, but nmake.exe is unavailable.
    echo Repair the Desktop development with C++ workload in Visual Studio Installer.
    goto :fail
)

echo.
echo Compiler detected:
where cl
cl 2>&1 | findstr /i /c:"Compiler" /c:"Microsoft"
echo.

echo [1/3] Configuring CMake...
cmake -S . -B build -G "NMake Makefiles" -DCMAKE_BUILD_TYPE=Release
if errorlevel 1 (
    echo.
    echo ERROR: CMake configuration failed.
    echo If this build directory was created with a different generator, delete the
    echo "build" folder once and run this launcher again.
    goto :fail
)

echo.
echo [2/3] Building NeuroChess...
cmake --build build --parallel
if errorlevel 1 (
    echo.
    echo ERROR: Compilation failed. The compiler output above contains the reason.
    goto :fail
)

set "ENGINE="
if exist "build\neurochess.exe" set "ENGINE=build\neurochess.exe"
if not defined ENGINE if exist "build\Release\neurochess.exe" set "ENGINE=build\Release\neurochess.exe"
if not defined ENGINE if exist "build\Debug\neurochess.exe" set "ENGINE=build\Debug\neurochess.exe"

if not defined ENGINE (
    echo.
    echo ERROR: Build finished, but neurochess.exe was not found.
    echo Searching the build directory:
    where /r build neurochess.exe 2>nul
    goto :fail
)

echo.
echo [3/3] Starting GUI with !ENGINE!...
python play_gui.py --engine "!ENGINE!"
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
