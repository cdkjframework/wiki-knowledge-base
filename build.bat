@echo off
REM Windows batch build script for knowledge-base project
REM Usage: build.bat

setlocal enabledelayedexpansion

REM Configuration
set "PROJECT_NAME=knowledge-base"
set "OUTPUT_DIR=dist"
set "VERSION=1.0.0"
set "PROJECT_ROOT=%~dp0"

REM Parse arguments
set "CLEAN_BUILD=0"
:parse_args
if "%~1"=="" goto start_build
if /i "%~1"=="--clean" (
    set "CLEAN_BUILD=1"
    shift
    goto parse_args
)
if /i "%~1"=="--output" (
    set "OUTPUT_DIR=%~2"
    shift
    shift
    goto parse_args
)
if /i "%~1"=="--version" (
    set "VERSION=%~2"
    shift
    shift
    goto parse_args
)
shift
goto parse_args

:start_build
echo.
echo [*] Starting build process for %PROJECT_NAME% v%VERSION%
echo [*] Project root: %PROJECT_ROOT%
echo.

REM Clean previous build
if %CLEAN_BUILD% equ 1 (
    if exist "%OUTPUT_DIR%" (
        echo [*] Cleaning previous build...
        rmdir /s /q "%OUTPUT_DIR%"
        echo [+] Cleaned %OUTPUT_DIR%
    )
)

REM Create output directory
if not exist "%OUTPUT_DIR%" (
    mkdir "%OUTPUT_DIR%"
    echo [+] Created output directory: %OUTPUT_DIR%
)

REM Copy source files
echo [*] Copying source files...
if exist "%PROJECT_ROOT%src" (
    xcopy "%PROJECT_ROOT%src" "%OUTPUT_DIR%\src" /E /I /Y >nul
    echo [+] Copied src directory
) else (
    echo [!] src directory not found
)

REM Copy web files
echo [*] Copying web files...
if exist "%PROJECT_ROOT%web" (
    xcopy "%PROJECT_ROOT%web" "%OUTPUT_DIR%\web" /E /I /Y >nul
    echo [+] Copied web directory
) else (
    echo [!] web directory not found
)

REM Copy configuration files
echo [*] Copying configuration files...
for %%F in (config.json requirements.txt README.md uninstall.ps1 uninstall.bat) do (
    if exist "%PROJECT_ROOT%%%F" (
        copy "%PROJECT_ROOT%%%F" "%OUTPUT_DIR%\%%F" >nul
        echo [+] Copied %%F
    )
)

REM Copy assets
if exist "%PROJECT_ROOT%assets" (
    echo [*] Copying assets...
    xcopy "%PROJECT_ROOT%assets" "%OUTPUT_DIR%\assets" /E /I /Y >nul
    echo [+] Copied assets directory
)

REM Copy docs
if exist "%PROJECT_ROOT%docs" (
    echo [*] Copying docs...
    xcopy "%PROJECT_ROOT%docs" "%OUTPUT_DIR%\docs" /E /I /Y >nul
    echo [+] Copied docs directory
)

REM Create startup batch file
echo [*] Creating startup scripts...

call :create_run_bat
call :create_run_ps1
call :create_setup_ps1
call :create_build_readme
call :create_manifest

echo.
echo [+] Build completed successfully!
echo [*] Output directory: %OUTPUT_DIR%
echo.
echo Next steps:
echo   1. cd %OUTPUT_DIR%
echo   2. setup.ps1     (first time setup - use PowerShell)
echo   3. run.bat       (start the server)
echo.
goto :eof

:create_run_bat
(
    echo @echo off
    echo setlocal enabledelayedexpansion
    echo.
    echo REM Activate virtual environment and start the application
    echo set "VENV_PATH=.venv\Scripts\activate.bat"
    echo set "PROJECT_ROOT=%%~dp0"
    echo.
    echo if exist "!PROJECT_ROOT!!VENV_PATH!" (
    echo     echo Activating virtual environment...
    echo     call "!PROJECT_ROOT!!VENV_PATH!"
    echo     echo Virtual environment activated
    echo     echo Starting knowledge-base server...
    echo     python -m src.main
    echo ) else (
    echo     echo Virtual environment not found at !PROJECT_ROOT!.venv
    echo     echo Please ensure the virtual environment is created and activated
    echo     exit /b 1
    echo )
    echo.
    echo endlocal
) > "%OUTPUT_DIR%\run.bat"
echo [+] Created run.bat
goto :eof

:create_run_ps1
(
    echo # Activate virtual environment and start the application
    echo $VenvPath = "\.venv\Scripts\Activate.ps1"
    echo $ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
    echo $ProjectRoot = $ScriptPath
    echo.
    echo if (Test-Path (Join-Path $ProjectRoot $VenvPath)) {
    echo     ^ (Join-Path $ProjectRoot $VenvPath^)
    echo     Write-Host "Virtual environment activated"
    echo     Write-Host "Starting knowledge-base server..."
    echo     python -m src.main
    echo } else {
    echo     Write-Host "Virtual environment not found at $ProjectRoot\.venv"
    echo     Write-Host "Please ensure the virtual environment is created and activated"
    echo     exit 1
    echo }
) > "%OUTPUT_DIR%\run.ps1"
echo [+] Created run.ps1
goto :eof

:create_setup_ps1
(
    echo # Setup script for first-time installation
    echo param(
    echo     [switch]$SkipVenv = $false
    echo )
    echo.
    echo $ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
    echo.
    echo Write-Host "Setting up knowledge-base project..."
    echo.
    echo # Create virtual environment if not exists
    echo if (-not (Test-Path "$ScriptPath\.venv") -and -not $SkipVenv) {
    echo     Write-Host "Creating virtual environment..."
    echo     python -m venv .venv
    echo     Write-Host "Virtual environment created"
    echo }
    echo.
    echo # Activate virtual environment
    echo $ActivateScript = "$ScriptPath\.venv\Scripts\Activate.ps1"
    echo if (Test-Path $ActivateScript) {
    echo     ^ $ActivateScript
    echo     Write-Host "Virtual environment activated"
    echo } else {
    echo     Write-Host "Warning: Could not find activation script"
    echo }
    echo.
    echo # Install requirements
    echo if (Test-Path "$ScriptPath\requirements.txt") {
    echo     Write-Host "Installing dependencies..."
    echo     if (Test-Path Env:PIP_REQUIRE_HASHES) {
    echo         Write-Host "Clearing PIP_REQUIRE_HASHES for dependency install..." -ForegroundColor Yellow
    echo         Remove-Item Env:PIP_REQUIRE_HASHES -ErrorAction SilentlyContinue
    echo     }
    echo     pip install -r requirements.txt
    echo     Write-Host "Dependencies installed successfully"
    echo } else {
    echo     Write-Host "Warning: requirements.txt not found"
    echo }
    echo.
    echo Write-Host "Setup complete! You can now run '.\run.ps1' or '.\run.bat' to start the server"
) > "%OUTPUT_DIR%\setup.ps1"
echo [+] Created setup.ps1
goto :eof

:create_build_readme
(
    echo # Knowledge-Base Distribution
    echo.
    echo ## Quick Start
    echo.
    echo ### Option 1: Using Command Prompt (Recommended)
    echo.
    echo 1. Run setup [first time only]:
    echo    ```
    echo    setup.ps1
    echo    ```
    echo    Or open PowerShell and run: `.\setup.ps1`
    echo.
    echo 2. Start the server:
    echo    ```
    echo    run.bat
    echo    ```
    echo.
    echo ### Option 2: Using PowerShell
    echo.
    echo 1. Run setup [first time only]:
    echo    ```powershell
    echo    .\setup.ps1
    echo    ```
    echo.
    echo 2. Start the server:
    echo    ```powershell
    echo    .\run.ps1
    echo    ```
    echo.
    echo ## Requirements
    echo.
    echo - Python 3.8 or later
    echo - Windows 7/8/10/11 or Server 2016+
    echo.
    echo ## Configuration
    echo.
    echo Edit `config.json` to configure:
    echo - Database settings (MySQL/PostgreSQL)
    echo - Redis session store
    echo - Model paths and cache
    echo - Chat model settings
    echo - LM Studio connection
    echo.
    echo ## Server Access
    echo.
    echo Once started, the server listens on: `http://127.0.0.1:5000`
    echo.
    echo - Web UI: `http://127.0.0.1:5000/ui/`
    echo - API Docs: `http://127.0.0.1:5000/docs/`
    echo.
    echo ## Project Structure
    echo.
    echo ```
    echo ├── src/                  # Source code
    echo ├── web/                  # Web UI files
    echo ├── config.json          # Configuration file
    echo ├── requirements.txt     # Python dependencies
    echo ├── run.ps1             # PowerShell startup script
    echo ├── run.bat             # Command prompt startup script
    echo ├── setup.ps1           # Setup/initialization script
    echo ├── uninstall.ps1       # PowerShell uninstall script
    echo └── uninstall.bat       # Batch uninstall script
    echo ```
    echo.
    echo ## Troubleshooting
    echo.
    echo ### Virtual Environment Issues
    echo - Ensure Python is in PATH: `python --version`
    echo - Delete `.venv` folder and run `setup.ps1` again
    echo.
    echo ### Dependencies
    echo - If pip install fails, check internet connection
    echo - Try: `pip install --upgrade pip`
    echo.
    echo ### Port Already in Use
    echo - Edit `config.json` to change the port
    echo - Or stop other applications using port 5000
    echo.
    echo ## Support
    echo.
    echo For more information, see README.md and docs/ directory.
) > "%OUTPUT_DIR%\BUILD_README.md"
echo [+] Created BUILD_README.md
goto :eof

:create_manifest
(
    echo {
    echo   "name": "%PROJECT_NAME%",
    echo   "version": "%VERSION%",
    echo   "buildDate": "%date% %time%",
    echo   "buildType": "windows",
    echo   "platform": "Windows"
    echo }
) > "%OUTPUT_DIR%\MANIFEST.json"
echo [+] Created MANIFEST.json
goto :eof

endlocal
