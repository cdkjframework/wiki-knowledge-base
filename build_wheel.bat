@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%build_wheel.ps1"

if not exist "%PS_SCRIPT%" (
    echo [x] build_wheel.ps1 not found: %PS_SCRIPT%
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo [x] Wheel build failed with exit code %EXIT_CODE%
) else (
    echo [+] Wheel build completed
)

exit /b %EXIT_CODE%
