# PowerShell Service Management Script for Knowledge-Base
# This script installs/uninstalls the Knowledge-Base application as a Windows service

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("install", "uninstall", "start", "stop", "restart", "status", "help")]
    [string]$Command = "help"
)

$ServiceName = "KnowledgeBase"
$ServiceDisplayName = "Knowledge-Base Service"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServiceScript = Join-Path $ProjectRoot "src\windows_service.py"
$VenvPath = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"

# Colors for output
$SuccessColor = "Green"
$ErrorColor = "Red"
$InfoColor = "Cyan"
$WarningColor = "Yellow"

function Write-Success {
    param([string]$Message)
    Write-Host "[+] $Message" -ForegroundColor $SuccessColor
}

function Write-Error-Custom {
    param([string]$Message)
    Write-Host "[!] $Message" -ForegroundColor $ErrorColor
}

function Write-Info {
    param([string]$Message)
    Write-Host "[*] $Message" -ForegroundColor $InfoColor
}

function Write-Warning-Custom {
    param([string]$Message)
    Write-Host "[*] $Message" -ForegroundColor $WarningColor
}

function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Show-Usage {
    Write-Host ""
    Write-Host "Knowledge-Base Windows Service Management" -ForegroundColor Cyan
    Write-Host "Usage: .\manage_service.ps1 -Command [command]"
    Write-Host ""
    Write-Host "Commands:"
    Write-Host "  install    - Install service"
    Write-Host "  uninstall  - Remove service"
    Write-Host "  start      - Start service"
    Write-Host "  stop       - Stop service"
    Write-Host "  restart    - Restart service"
    Write-Host "  status     - Check service status"
    Write-Host "  help       - Show this help message"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\manage_service.ps1 -Command install"
    Write-Host "  .\manage_service.ps1 -Command start"
    Write-Host "  .\manage_service.ps1 -Command status"
    Write-Host ""
}

function Install-Service {
    Write-Info "Installing $ServiceDisplayName..."
    Write-Info "Service Name: $ServiceName"
    Write-Info "Project Root: $ProjectRoot"
    Write-Info "Service Script: $ServiceScript"
    Write-Host ""
    
    # Check if service already exists
    $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($service) {
        Write-Warning-Custom "Service '$ServiceName' already exists"
        Write-Info "Removing existing service..."
        
        # Stop the service
        try {
            Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        } catch {
            Write-Warning-Custom "Could not stop existing service"
        }
        
        # Remove the service
        & $ServiceScript remove
        Start-Sleep -Seconds 2
    }
    
    # Check for pywin32
    Write-Info "Checking for pywin32..."
    try {
        Import-Module win32 -ErrorAction Stop
    } catch {
        Write-Info "Installing pywin32..."
        & pip install pywin32 --quiet
        
        if ($LASTEXITCODE -eq 0) {
            Write-Success "pywin32 installed"
            
            Write-Info "Running pywin32 post-install..."
            & python -m Scripts.pywin32_postinstall -install
        } else {
            Write-Error-Custom "Failed to install pywin32"
            return
        }
    }
    
    # Check virtual environment
    if (-not (Test-Path $VenvPath)) {
        Write-Error-Custom "Virtual environment not found at $VenvPath"
        Write-Info "Please run setup.ps1 first to create virtual environment"
        return
    }
    
    # Activate virtual environment
    Write-Info "Activating virtual environment..."
    & $VenvPath
    
    # Install service
    Write-Info "Creating service..."
    & python $ServiceScript install
    
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Service installed successfully"
        Write-Host ""
        Write-Host "Service Details:" -ForegroundColor Cyan
        Write-Host "  - Name: $ServiceName"
        Write-Host "  - Display Name: $ServiceDisplayName"
        Write-Host "  - Status: Stopped"
        Write-Host ""
        Write-Host "Next steps:" -ForegroundColor Cyan
        Write-Host "  1. Run: .\manage_service.ps1 -Command start"
        Write-Host "  2. Monitor: .\manage_service.ps1 -Command status"
        Write-Host ""
        Write-Host "To uninstall later, run: .\manage_service.ps1 -Command uninstall"
        Write-Host ""
    } else {
        Write-Error-Custom "Failed to install service"
    }
}

function Uninstall-Service {
    Write-Info "Uninstalling $ServiceDisplayName..."
    Write-Host ""
    
    # Check if service exists
    $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if (-not $service) {
        Write-Error-Custom "Service '$ServiceName' not found"
        return
    }
    
    # Stop service
    Write-Info "Stopping service..."
    try {
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 3
    } catch {
        Write-Warning-Custom "Could not stop service"
    }
    
    # Activate virtual environment
    if (Test-Path $VenvPath) {
        & $VenvPath
    }
    
    # Remove service
    Write-Info "Removing service..."
    & python $ServiceScript remove
    
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Service uninstalled successfully"
    } else {
        Write-Error-Custom "Failed to uninstall service"
    }
    Write-Host ""
}

function Start-KBService {
    Write-Info "Starting $ServiceName..."
    Write-Host ""
    
    $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if (-not $service) {
        Write-Error-Custom "Service '$ServiceName' not found"
        return
    }
    
    try {
        Start-Service -Name $ServiceName
        Start-Sleep -Seconds 2
        
        $service = Get-Service -Name $ServiceName
        if ($service.Status -eq "Running") {
            Write-Success "Service started (Status: $($service.Status))"
        } else {
            Write-Warning-Custom "Service status: $($service.Status)"
        }
    } catch {
        Write-Error-Custom "Failed to start service: $_"
    }
    Write-Host ""
}

function Stop-KBService {
    Write-Info "Stopping $ServiceName..."
    Write-Host ""
    
    $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if (-not $service) {
        Write-Error-Custom "Service '$ServiceName' not found"
        return
    }
    
    try {
        Stop-Service -Name $ServiceName -Force
        Write-Success "Service stopped"
    } catch {
        Write-Error-Custom "Failed to stop service: $_"
    }
    Write-Host ""
}

function Restart-KBService {
    Write-Info "Restarting $ServiceName..."
    Write-Host ""
    
    Stop-KBService
    Start-Sleep -Seconds 2
    Start-KBService
}

function Get-KBServiceStatus {
    Write-Host ""
    Write-Host "Service Status for '$ServiceName':" -ForegroundColor Cyan
    Write-Host ""
    
    $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($service) {
        Write-Host "Service Name      : $($service.Name)"
        Write-Host "Display Name      : $($service.DisplayName)"
        Write-Host "Status            : $($service.Status)"
        Write-Host "Start Type        : $($service.StartType)"
        
        # Get process info if running
        if ($service.Status -eq "Running") {
            $process = Get-Process -Name "python" -ErrorAction SilentlyContinue | 
                Where-Object { $_.CommandLine -like "*windows_service*" }
            if ($process) {
                Write-Host "Process ID (PID)  : $($process.Id)"
                Write-Host "Memory Usage      : $([math]::Round($process.WorkingSet / 1MB, 2)) MB"
            }
        }
    } else {
        Write-Error-Custom "Service '$ServiceName' not found"
    }
    Write-Host ""
}

# Main logic
if (-not (Test-Administrator)) {
    Write-Error-Custom "This script requires Administrator privileges"
    Write-Info "Please run PowerShell as Administrator and try again"
    exit 1
}

switch ($Command) {
    "install" {
        Install-Service
    }
    "uninstall" {
        Uninstall-Service
    }
    "start" {
        Start-KBService
    }
    "stop" {
        Stop-KBService
    }
    "restart" {
        Restart-KBService
    }
    "status" {
        Get-KBServiceStatus
    }
    default {
        Show-Usage
    }
}
