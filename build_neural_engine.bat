@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

if "%~1"=="" (
    echo ERROR: ONNX Runtime root path was not supplied.
    exit /b 2
)
set "ORT_ROOT=%~1"

where cmake >nul 2>nul
if errorlevel 1 (
    echo ERROR: CMake was not found in PATH.
    exit /b 2
)

where cl >nul 2>nul
if errorlevel 1 (
    set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
    if exist "!VSWHERE!" (
        for /f "tokens=*" %%i in ('"!VSWHERE!" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath') do set "VSINSTALL=%%i"
    )
    if defined VSINSTALL if exist "!VSINSTALL!\VC\Auxiliary\Build\vcvars64.bat" (
        call "!VSINSTALL!\VC\Auxiliary\Build\vcvars64.bat" >nul
    )
)

where cl >nul 2>nul
if errorlevel 1 (
    echo ERROR: MSVC C++ compiler is unavailable.
    exit /b 2
)

if not exist "!ORT_ROOT!\include\onnxruntime_cxx_api.h" (
    echo ERROR: Invalid ONNX Runtime root: !ORT_ROOT!
    exit /b 2
)

if exist build-neural rmdir /s /q build-neural

echo Configuring NeuroChess with ONNX Runtime...
cmake -S . -B build-neural -G "NMake Makefiles" -DCMAKE_BUILD_TYPE=Release -DNEUROCHESS_ENABLE_ONNX=ON -DONNXRUNTIME_ROOT="!ORT_ROOT!"
if errorlevel 1 exit /b 2

echo Building neural NeuroChess...
cmake --build build-neural --parallel
if errorlevel 1 exit /b 2

if exist "!ORT_ROOT!\lib\onnxruntime.dll" copy /y "!ORT_ROOT!\lib\onnxruntime.dll" "build-neural\onnxruntime.dll" >nul
if not exist "build-neural\neurochess.exe" (
    echo ERROR: build-neural\neurochess.exe was not created.
    exit /b 2
)

echo Neural engine ready: %CD%\build-neural\neurochess.exe
exit /b 0
