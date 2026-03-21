# Windows PowerShell build script for knowledge-base project
# Usage: .\build.ps1

param(
    [switch]$Clean = $false,
    [string]$OutputDir = "./dist",
    [string]$Version = "1.0.0"
)

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectName = "knowledge-base"

# Colors for output
$SuccessColor = "Green"
$ErrorColor = "Red"
$InfoColor = "Cyan"

function Write-Success {
    param([string]$Message)
    Write-Host "[✓] $Message" -ForegroundColor $SuccessColor
}

function Write-Error-Custom {
    param([string]$Message)
    Write-Host "[✗] $Message" -ForegroundColor $ErrorColor
}

function Write-Info {
    param([string]$Message)
    Write-Host "[*] $Message" -ForegroundColor $InfoColor
}

# Main build process
function Invoke-Build {
    Write-Info "Starting build process for $ProjectName v$Version"
    Write-Info "Project root: $ProjectRoot"
    
    # Clean previous build
    if ($Clean -and (Test-Path $OutputDir)) {
        Write-Info "Cleaning previous build..."
        Remove-Item $OutputDir -Recurse -Force
        Write-Success "Cleaned $OutputDir"
    }
    
    # Create output directory
    if (-not (Test-Path $OutputDir)) {
        New-Item -ItemType Directory -Path $OutputDir | Out-Null
        Write-Success "Created output directory: $OutputDir"
    }
    
    # Copy source files
    Write-Info "Copying source files..."
    Copy-Item -Path "$ProjectRoot\src" -Destination "$OutputDir\src" -Recurse -Force
    Write-Success "Copied src directory"
    
    # Copy web files
    Write-Info "Copying web files..."
    Copy-Item -Path "$ProjectRoot\web" -Destination "$OutputDir\web" -Recurse -Force
    Write-Success "Copied web directory"
    
    # Copy configuration and data files
    Write-Info "Copying configuration files..."
    $ConfigFiles = @(
        "config.json",
        "requirements.txt",
        "README.md",
        "uninstall.ps1",
        "uninstall.bat"
    )
    
    foreach ($File in $ConfigFiles) {
        $SourcePath = Join-Path $ProjectRoot $File
        if (Test-Path $SourcePath) {
            Copy-Item -Path $SourcePath -Destination $OutputDir
            Write-Success "Copied $File"
        }
    }
    
    # Copy assets if exists
    if (Test-Path "$ProjectRoot\assets") {
        Write-Info "Copying assets..."
        Copy-Item -Path "$ProjectRoot\assets" -Destination "$OutputDir\assets" -Recurse -Force
        Write-Success "Copied assets directory"
    }
    
    # Copy docs if exists
    if (Test-Path "$ProjectRoot\docs") {
        Write-Info "Copying docs..."
        Copy-Item -Path "$ProjectRoot\docs" -Destination "$OutputDir\docs" -Recurse -Force
        Write-Success "Copied docs directory"
    }
    
    # Create startup batch files
    Write-Info "Creating startup scripts..."
    
    # PowerShell startup script
    $PSStartScript = @"
# Activate virtual environment and start the application
`$VenvPath = "\.venv\Scripts\Activate.ps1"
`$ScriptPath = Split-Path -Parent `$MyInvocation.MyCommand.Path
`$ProjectRoot = `$ScriptPath

if (Test-Path (Join-Path `$ProjectRoot `$VenvPath)) {
    & (Join-Path `$ProjectRoot `$VenvPath)
    Write-Host "Virtual environment activated"
    Write-Host "Starting knowledge-base server..."
    python -m src.main
} else {
    Write-Host "Virtual environment not found at `$ProjectRoot\.venv"
    Write-Host "Please ensure the virtual environment is created and activated"
    exit 1
}
"@
    
    Set-Content -Path "$OutputDir\run.ps1" -Value $PSStartScript
    Write-Success "Created run.ps1"
    
    # Batch startup script
    $BatStartScript = @"
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
"@
    
    Set-Content -Path "$OutputDir\run.bat" -Value $BatStartScript
    Write-Success "Created run.bat"
    
    # Setup script
    $SetupScript = @"
# Setup script for first-time installation
param(
    [switch]`$SkipVenv = `$false
)

`$ScriptPath = Split-Path -Parent `$MyInvocation.MyCommand.Path

Write-Host "Setting up knowledge-base project..."

# Create virtual environment if not exists
if (-not (Test-Path "`$ScriptPath\.venv") -and -not `$SkipVenv) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
    Write-Host "Virtual environment created"
}

# Activate virtual environment
`$ActivateScript = "`$ScriptPath\.venv\Scripts\Activate.ps1"
if (Test-Path `$ActivateScript) {
    & `$ActivateScript
    Write-Host "Virtual environment activated"
} else {
    Write-Host "Warning: Could not find activation script"
}

# Install requirements
if (Test-Path "`$ScriptPath\requirements.txt") {
    Write-Host "Installing dependencies..."
    if (Test-Path Env:PIP_REQUIRE_HASHES) {
        Write-Host "Clearing PIP_REQUIRE_HASHES for dependency install..." -ForegroundColor Yellow
        Remove-Item Env:PIP_REQUIRE_HASHES -ErrorAction SilentlyContinue
    }
    pip install -r requirements.txt
    Write-Host "Dependencies installed successfully"
} else {
    Write-Host "Warning: requirements.txt not found"
}

Write-Host "Setup complete! You can now run '.\run.ps1' or '.\run.bat' to start the server"
"@
    
    Set-Content -Path "$OutputDir\setup.ps1" -Value $SetupScript
    Write-Success "Created setup.ps1"
    
    # Create README for build
    $BuildReadme = @"
# Knowledge-Base Distribution

## Quick Start

### Option 1: Using PowerShell

1. Run setup (first time only):
   ```powershell
   .\setup.ps1
   ```

2. Start the server:
   ```powershell
   .\run.ps1
   ```

### Option 2: Using Command Prompt

1. Run setup (first time only):
   ```cmd
   setup.ps1
   ```
   Or use PowerShell to run setup first

2. Start the server:
   ```cmd
   run.bat
   ```

## Requirements

- Python 3.8 or later
- Windows 7/8/10/11 or Server 2016+

## Configuration

Edit `config.json` to configure:
- Database settings (MySQL/PostgreSQL)
- Redis session store
- Model paths and cache
- Chat model settings
- LM Studio connection

## Server Access

Once started, the server listens on: `http://127.0.0.1:5000`

- Web UI: `http://127.0.0.1:5000/ui/`
- API Docs: `http://127.0.0.1:5000/docs/`

## Project Structure

```
├── src/                  # Source code
├── web/                  # Web UI files
├── config.json          # Configuration file
├── requirements.txt     # Python dependencies
├── run.ps1             # PowerShell startup script
├── run.bat             # Command prompt startup script
├── setup.ps1           # Setup/initialization script
├── uninstall.ps1       # PowerShell uninstall script
└── uninstall.bat       # Batch uninstall script
```

## Troubleshooting

### Virtual Environment Issues
- Ensure Python is in PATH: `python --version`
- Delete `.venv` folder and run `setup.ps1` again

### Dependencies
- If pip install fails, check internet connection
- Try: `pip install --upgrade pip`

### Port Already in Use
- Edit `config.json` to change the port
- Or stop other applications using port 5000

## Support

For more information, see README.md and docs/ directory.
"@
    
    Set-Content -Path "$OutputDir\BUILD_README.md" -Value $BuildReadme
    Write-Success "Created BUILD_README.md"
    
    # Create manifest file with build info
    $Manifest = @{
        name = $ProjectName
        version = $Version
        buildDate = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        buildType = "windows"
        python = (python --version 2>&1)
    } | ConvertTo-Json
    
    Set-Content -Path "$OutputDir\MANIFEST.json" -Value $Manifest
    Write-Success "Created MANIFEST.json"
}

# Run build
try {
    Invoke-Build
    Write-Success "Build completed successfully!"
    Write-Info "Output directory: $OutputDir"
    Write-Host ""
    Write-Host "Next steps:"
    Write-Host "  1. cd $OutputDir"
    Write-Host "  2. .\setup.ps1     (first time setup)"
    Write-Host "  3. .\run.ps1       (start the server)"
} catch {
    Write-Error-Custom "Build failed: $_"
    exit 1
}
