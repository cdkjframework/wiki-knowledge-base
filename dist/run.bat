@echo off
setlocal enabledelayedexpansion

REM Activate virtual environment and start the application
set "VENV_PATH=.venv\Scripts\activate.bat"
set "PROJECT_ROOT=%~dp0"

if exist "!PROJECT_ROOT!!VENV_PATH!" (
    echo Activating virtual environment...
    call "!PROJECT_ROOT!!VENV_PATH!"
    echo Virtual environment activated
    echo Starting knowledge-base server...
    python -m src.main
) else (
    echo Virtual environment not found at !PROJECT_ROOT!.venv
    echo Please ensure the virtual environment is created and activated
    exit /b 1
)

endlocal
