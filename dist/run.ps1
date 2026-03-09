# Activate virtual environment and start the application
$VenvPath = "\.venv\Scripts\Activate.ps1"
$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = $ScriptPath

if (Test-Path (Join-Path $ProjectRoot $VenvPath)) {
    & (Join-Path $ProjectRoot $VenvPath)
    Write-Host "Virtual environment activated"
    Write-Host "Starting knowledge-base server..."
    python -m src.main
} else {
    Write-Host "Virtual environment not found at $ProjectRoot\.venv"
    Write-Host "Please ensure the virtual environment is created and activated"
    exit 1
}
