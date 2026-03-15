param(
    [string]$ServiceName = "KnowledgeBase",
    [switch]$RemoveVenv,
    [switch]$RemoveData,
    [switch]$RemoveModels,
    [switch]$Force,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServiceScript = Join-Path $ProjectRoot "src\windows_service.py"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

function Write-Info {
    param([string]$Message)
    Write-Host "[*] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[+] $Message" -ForegroundColor Green
}

function Write-Warning-Custom {
    param([string]$Message)
    Write-Host "[!] $Message" -ForegroundColor Yellow
}

function Write-Error-Custom {
    param([string]$Message)
    Write-Host "[x] $Message" -ForegroundColor Red
}

function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Show-Usage {
    Write-Host ""
    Write-Host "Knowledge-Base Uninstall Script" -ForegroundColor Cyan
    Write-Host "Usage: .\uninstall.ps1 [options]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -ServiceName <name>  Service name to uninstall (default: KnowledgeBase)"
    Write-Host "  -RemoveVenv          Remove .venv directory"
    Write-Host "  -RemoveData          Remove kb_store and logs directories"
    Write-Host "  -RemoveModels        Remove models\hf_cache directory"
    Write-Host "  -Force               Skip confirmation prompts"
    Write-Host "  -Help                Show this help"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\uninstall.ps1"
    Write-Host "  .\uninstall.ps1 -RemoveData"
    Write-Host "  .\uninstall.ps1 -RemoveVenv -RemoveData -Force"
    Write-Host ""
}

function Confirm-Action {
    param(
        [string]$Prompt,
        [switch]$AutoApprove
    )

    if ($AutoApprove) {
        return $true
    }

    $answer = Read-Host "$Prompt [y/N]"
    return $answer -match '^(y|yes)$'
}

function Remove-PathSafe {
    param(
        [string]$PathToRemove,
        [string]$Label,
        [switch]$AutoApprove
    )

    if (-not (Test-Path $PathToRemove)) {
        Write-Info "$Label not found, skipping: $PathToRemove"
        return
    }

    if (-not (Confirm-Action -Prompt "Delete $Label ($PathToRemove)?" -AutoApprove:$AutoApprove)) {
        Write-Info "Skipped $Label"
        return
    }

    Remove-Item -Path $PathToRemove -Recurse -Force
    Write-Success "Removed $Label"
}

if ($Help) {
    Show-Usage
    exit 0
}

if (-not (Test-Administrator)) {
    Write-Error-Custom "This script requires Administrator privileges."
    Write-Info "Please run PowerShell as Administrator and try again."
    exit 1
}

Write-Info "Project root: $ProjectRoot"
Write-Info "Uninstalling service: $ServiceName"

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($service) {
    if ($service.Status -ne "Stopped") {
        Write-Info "Stopping service $ServiceName ..."
        try {
            Stop-Service -Name $ServiceName -Force -ErrorAction Stop
            Start-Sleep -Seconds 2
            Write-Success "Service stopped"
        } catch {
            Write-Warning-Custom "Failed to stop service via Stop-Service: $_"
        }
    }

    $removed = $false
    if (Test-Path $ServiceScript) {
        if (Test-Path $VenvPython) {
            Write-Info "Removing service via venv python ..."
            & $VenvPython $ServiceScript remove
            if ($LASTEXITCODE -eq 0) {
                $removed = $true
            }
        } else {
            Write-Info "Removing service via system python ..."
            python $ServiceScript remove
            if ($LASTEXITCODE -eq 0) {
                $removed = $true
            }
        }
    }

    if (-not $removed) {
        Write-Warning-Custom "Service script removal failed, trying sc.exe delete ..."
        sc.exe delete $ServiceName | Out-Null
        Start-Sleep -Seconds 1
    }

    $stillExists = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($stillExists) {
        Write-Warning-Custom "Service still exists, it may be marked for deletion until all handles are released."
    } else {
        Write-Success "Service removed"
    }
} else {
    Write-Info "Service '$ServiceName' does not exist, skipping service uninstall."
}

if ($RemoveData) {
    Remove-PathSafe -PathToRemove (Join-Path $ProjectRoot "kb_store") -Label "knowledge store directory" -AutoApprove:$Force
    Remove-PathSafe -PathToRemove (Join-Path $ProjectRoot "logs") -Label "logs directory" -AutoApprove:$Force
}

if ($RemoveModels) {
    Remove-PathSafe -PathToRemove (Join-Path $ProjectRoot "models\hf_cache") -Label "model cache directory" -AutoApprove:$Force
}

if ($RemoveVenv) {
    Remove-PathSafe -PathToRemove (Join-Path $ProjectRoot ".venv") -Label "virtual environment" -AutoApprove:$Force
}

Write-Host ""
Write-Success "Uninstall flow completed."
