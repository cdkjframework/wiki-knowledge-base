@echo off
REM Windows Service Management Script for Knowledge-Base
REM This script installs/uninstalls the Knowledge-Base application as a Windows service

setlocal enabledelayedexpansion

set "SERVICE_NAME=KnowledgeBase"
set "SERVICE_DISPLAY_NAME=Knowledge-Base Service"
set "PROJECT_ROOT=%~dp0"
set "PYTHON_EXE=python.exe"
set "SERVICE_SCRIPT=%PROJECT_ROOT%src\windows_service.py"

REM Check for Administrator privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Error: This script requires Administrator privileges
    echo [*] Please run Command Prompt as Administrator and try again
    pause
    exit /b 1
)

REM Parse command line arguments
if "%~1"=="" goto show_usage
if /i "%~1"=="install" goto install_service
if /i "%~1"=="uninstall" goto uninstall_service
if /i "%~1"=="start" goto start_service
if /i "%~1"=="stop" goto stop_service
if /i "%~1"=="restart" goto restart_service
if /i "%~1"=="status" goto service_status
if /i "%~1"=="help" goto show_usage
goto show_usage

:show_usage
echo.
echo Knowledge-Base Windows Service Management
echo Usage: manage_service.bat [command]
echo.
echo Commands:
echo   install    - Install service
echo   uninstall  - Remove service
echo   start      - Start service
echo   stop       - Stop service
echo   restart    - Restart service
echo   status     - Check service status
echo   help       - Show this help message
echo.
echo Examples:
echo   manage_service.bat install
echo   manage_service.bat start
echo   manage_service.bat stop
echo.
goto :eof

:install_service
echo.
echo [*] Installing %SERVICE_DISPLAY_NAME%...
echo [*] Service Name: %SERVICE_NAME%
echo [*] Project Root: %PROJECT_ROOT%
echo [*] Service Script: %SERVICE_SCRIPT%
echo.

REM Check if pywin32 is installed
echo [*] Checking for pywin32...
python -c "import win32serviceutil" >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] pywin32 is not installed
    echo [*] Installing pywin32...
    pip install pywin32
    if %errorlevel% neq 0 (
        echo [!] Failed to install pywin32
        pause
        exit /b 1
    )
    
    REM Post-install steps for pywin32
    echo [*] Running pywin32 post-install...
    python -m Scripts.pywin32_postinstall -install
    if %errorlevel% neq 0 (
        echo [!] Warning: pywin32 post-install had issues
    )
)

REM Activate virtual environment
echo [*] Activating virtual environment...
if exist "%PROJECT_ROOT%.venv\Scripts\activate.bat" (
    call "%PROJECT_ROOT%.venv\Scripts\activate.bat"
) else (
    echo [!] Virtual environment not found
    echo [*] Please run setup.ps1 first to create virtual environment
    pause
    exit /b 1
)

REM Check if service already exists
sc query %SERVICE_NAME% >nul 2>&1
if %errorlevel% equ 0 (
    echo [!] Service '%SERVICE_NAME%' already exists
    echo [*] Removing existing service...
    sc stop %SERVICE_NAME% >nul 2>&1
    timeout /t 2 /nobreak
    sc delete %SERVICE_NAME% >nul 2>&1
    timeout /t 2 /nobreak
)

REM Create service
echo [*] Creating service...
python "%SERVICE_SCRIPT%" install
if %errorlevel% equ 0 (
    echo [+] Service installed successfully
    echo.
    echo [*] Service Details:
    echo   - Name: %SERVICE_NAME%
    echo   - Display Name: %SERVICE_DISPLAY_NAME%
    echo   - Status: Stopped
    echo.
    echo [*] Next steps:
    echo   1. Run: manage_service.bat start
    echo   2. Monitor status: manage_service.bat status
    echo.
    echo [*] To uninstall later, run: manage_service.bat uninstall
) else (
    echo [!] Failed to install service
    pause
    exit /b 1
)
goto :eof

:uninstall_service
echo.
echo [*] Uninstalling %SERVICE_DISPLAY_NAME%...
echo.

REM Check if service exists
sc query %SERVICE_NAME% >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Service '%SERVICE_NAME%' not found
    goto :eof
)

REM Stop service first
echo [*] Stopping service...
sc stop %SERVICE_NAME% >nul 2>&1
timeout /t 3 /nobreak

REM Activate virtual environment
if exist "%PROJECT_ROOT%.venv\Scripts\activate.bat" (
    call "%PROJECT_ROOT%.venv\Scripts\activate.bat"
)

REM Remove service
echo [*] Removing service...
python "%SERVICE_SCRIPT%" remove
if %errorlevel% equ 0 (
    echo [+] Service uninstalled successfully
) else (
    echo [!] Failed to uninstall service
)
goto :eof

:start_service
echo.
echo [*] Starting %SERVICE_NAME%...
sc start %SERVICE_NAME%
if %errorlevel% equ 0 (
    echo [+] Service started
    timeout /t 2 /nobreak
    call :service_status
) else (
    echo [!] Failed to start service
)
goto :eof

:stop_service
echo.
echo [*] Stopping %SERVICE_NAME%...
sc stop %SERVICE_NAME%
if %errorlevel% equ 0 (
    echo [+] Service stopped
) else (
    echo [!] Failed to stop service
)
goto :eof

:restart_service
echo.
echo [*] Restarting %SERVICE_NAME%...
call :stop_service
timeout /t 2 /nobreak
call :start_service
goto :eof

:service_status
echo.
echo [*] Service Status for '%SERVICE_NAME%':
echo.
sc query %SERVICE_NAME%
echo.
goto :eof

endlocal
