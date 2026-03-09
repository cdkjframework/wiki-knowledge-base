# Setup script for first-time installation
param(
    [switch]$SkipVenv = $false
)

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Setting up knowledge-base project..."

# Create virtual environment if not exists
if (-not (Test-Path "$ScriptPath\.venv") -and -not $SkipVenv) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
    Write-Host "Virtual environment created"
}

# Activate virtual environment
$ActivateScript = "$ScriptPath\.venv\Scripts\Activate.ps1"
if (Test-Path $ActivateScript) {
    & $ActivateScript
    Write-Host "Virtual environment activated"
} else {
    Write-Host "Warning: Could not find activation script"
}

# Install requirements
if (Test-Path "$ScriptPath\requirements.txt") {
    Write-Host "Installing dependencies..."
    pip install -r requirements.txt
    Write-Host "Dependencies installed successfully"
} else {
    Write-Host "Warning: requirements.txt not found"
}

Write-Host "Setup complete! You can now run '.\run.ps1' or '.\run.bat' to start the server"
