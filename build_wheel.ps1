param(
    [switch]$Clean = $true,
    [string]$OutputDir = "./dist",
    [string]$BundleName = "knowledge-base-deploy"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$OutputPath = Join-Path $ProjectRoot $OutputDir
$PyprojectPath = Join-Path $ProjectRoot "pyproject.toml"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PythonExe = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

function Write-Info {
    param([string]$Message)
    Write-Host "[*] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[+] $Message" -ForegroundColor Green
}

function Write-Error-Custom {
    param([string]$Message)
    Write-Host "[x] $Message" -ForegroundColor Red
}

function Write-Warning-Custom {
    param([string]$Message)
    Write-Host "[!] $Message" -ForegroundColor Yellow
}

function Copy-IfExists {
    param(
        [string]$Source,
        [string]$Destination,
        [switch]$IsDirectory
    )

    if (-not (Test-Path $Source)) {
        Write-Warning-Custom "Skip missing path: $Source"
        return
    }

    if ($IsDirectory) {
        Copy-Item -Path $Source -Destination $Destination -Recurse -Force
    } else {
        Copy-Item -Path $Source -Destination $Destination -Force
    }
}

function New-TarGzArchive {
    param(
        [string]$SourceDirectory,
        [string]$ArchivePath
    )

    $tarCmd = Get-Command tar -ErrorAction SilentlyContinue
    if (-not $tarCmd) {
        throw "'tar' command not found. Please install tar (Windows bsdtar/Git Bash tar or Linux tar)."
    }

    if (Test-Path $ArchivePath) {
        Remove-Item -Path $ArchivePath -Force
    }

    $parentDir = Split-Path -Parent $SourceDirectory
    $leafDir = Split-Path -Leaf $SourceDirectory

    Push-Location $parentDir
    try {
        & tar -czf $ArchivePath $leafDir
        if ($LASTEXITCODE -ne 0) {
            throw "tar.gz archive creation failed"
        }
    }
    finally {
        Pop-Location
    }
}

function New-DeployScripts {
    param([string]$Destination)

    $installScript = @'
param(
    [switch]$SkipVenv = $false,
    [switch]$SkipCudaTorch = $false
)

function Select-PythonCommand {
    $candidates = New-Object System.Collections.ArrayList

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        try {
            $pyList = & py -0p 2>$null
            foreach ($line in $pyList) {
                $t = $line.Trim()
                if ([string]::IsNullOrWhiteSpace($t)) {
                    continue
                }

                $exePath = $null
                $m = [regex]::Match($t, '([A-Za-z]:\\[^\s]+python\.exe)')
                if ($m.Success) {
                    $exePath = $m.Groups[1].Value
                }

                if (-not $exePath) {
                    $parts = $t -split '\\s+'
                    if ($parts.Count -gt 0) {
                        $lastPart = $parts[$parts.Count - 1]
                        if (Test-Path $lastPart) {
                            $exePath = $lastPart
                        }
                    }
                }

                if ($exePath -and -not $candidates.Contains($exePath)) {
                    [void]$candidates.Add($exePath)
                }
            }
        } catch {
        }
    }

    foreach ($cmd in @("python", "python3")) {
        $resolved = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($resolved -and -not $candidates.Contains($resolved.Source)) {
            [void]$candidates.Add($resolved.Source)
        }
    }

    # Filter to minimum version 3.12
    $qualified = New-Object System.Collections.ArrayList
    foreach ($exe in $candidates) {
        try {
            $verStr = & $exe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            $parts = $verStr.Trim() -split '\.'
            if ($parts.Count -ge 2) {
                $major = [int]$parts[0]
                $minor = [int]$parts[1]
                if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 12)) {
                    [void]$qualified.Add($exe)
                } else {
                    Write-Host "[!] Skipping $exe (Python $verStr, requires >= 3.12)" -ForegroundColor Yellow
                }
            }
        } catch {}
    }

    if ($qualified.Count -eq 0) {
        throw "No Python 3.12+ interpreter found. Please install Python 3.12 or higher and retry."
    }

    if ($qualified.Count -eq 1) {
        return [string]$qualified[0]
    }

    $candidates = $qualified

    Write-Host "[*] Multiple Python 3.12+ interpreters detected. Please choose one:" -ForegroundColor Cyan
    for ($i = 0; $i -lt $candidates.Count; $i++) {
        $ver = & $candidates[$i] -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>$null
        Write-Host "[$($i + 1)] $($candidates[$i])  (Python $($ver.Trim()))"
    }

    while ($true) {
        $choice = Read-Host "Enter number (1-$($candidates.Count))"
        $idx = 0
        if ([int]::TryParse($choice, [ref]$idx)) {
            if ($idx -ge 1 -and $idx -le $candidates.Count) {
                return [string]$candidates[$idx - 1]
            }
        }
        Write-Host "[!] Invalid selection, please try again." -ForegroundColor Yellow
    }
}

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptPath

$PythonCmd = Select-PythonCommand
Write-Host "[*] Using Python: $PythonCmd" -ForegroundColor Cyan

if (-not (Test-Path ".venv") -and -not $SkipVenv) {
    Write-Host "[*] Creating virtual environment..." -ForegroundColor Cyan
    & $PythonCmd -m venv .venv
}

if (Test-Path ".venv\Scripts\Activate.ps1") {
    & ".\.venv\Scripts\Activate.ps1"
}

Write-Host "[*] Installing dependencies..." -ForegroundColor Cyan
pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    throw "pip install -r requirements.txt failed"
}

if (-not $SkipCudaTorch) {
    $hasNvidia = $false
    $hasAmd = $false
    try {
        if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) { $hasNvidia = $true }
    } catch {}
    try {
        if (Get-Command rocm-smi -ErrorAction SilentlyContinue) { $hasAmd = $true }
    } catch {}

    if ($hasNvidia) {
        Write-Host "[*] NVIDIA GPU detected, installing CUDA torch wheel (cu121)..." -ForegroundColor Cyan
        pip install --force-reinstall torch==2.2.2 --index-url https://download.pytorch.org/whl/cu121
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[!] CUDA torch install failed, keep current torch package" -ForegroundColor Yellow
        }

        Write-Host "[*] NVIDIA GPU detected, trying FAISS GPU package..." -ForegroundColor Cyan
        pip install --force-reinstall faiss-gpu==1.8.0
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[!] faiss-gpu install failed, fallback to faiss-cpu" -ForegroundColor Yellow
            pip install --force-reinstall faiss-cpu==1.8.0
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to install both faiss-gpu and faiss-cpu"
            }
        }
    } elseif ($hasAmd) {
        Write-Host "[*] AMD GPU detected, installing ROCm torch wheel (rocm6.0)..." -ForegroundColor Cyan
        pip install --force-reinstall torch==2.2.2 --index-url https://download.pytorch.org/whl/rocm6.0
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[!] ROCm torch install failed, keep current torch package" -ForegroundColor Yellow
        }
        Write-Host "[!] faiss-gpu is not supported on AMD ROCm, using faiss-cpu" -ForegroundColor Yellow
        pip install --force-reinstall faiss-cpu==1.8.0
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install faiss-cpu"
        }
    }
}

$wheel = Get-ChildItem -Path $ScriptPath -Filter "*.whl" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($wheel) {
    Write-Host "[*] Installing wheel package: $($wheel.Name)" -ForegroundColor Cyan
    pip install --force-reinstall --no-deps $wheel.FullName
    if ($LASTEXITCODE -ne 0) {
        throw "pip install wheel failed"
    }
} else {
    throw "No wheel found in current directory"
}

Write-Host "[+] Install completed" -ForegroundColor Green
'@

    $runPsScript = @'
$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptPath
$env:KB_PROJECT_ROOT = $ScriptPath

if (Test-Path ".venv\Scripts\Activate.ps1") {
    & ".\.venv\Scripts\Activate.ps1"
}

$localCmd = Join-Path $ScriptPath ".venv\Scripts\knowledge-base.exe"
$localCmdNoExt = Join-Path $ScriptPath ".venv\Scripts\knowledge-base"
if (Test-Path $localCmd) {
    & $localCmd
} elseif (Test-Path $localCmdNoExt) {
    & $localCmdNoExt
} elseif (Get-Command "knowledge-base" -ErrorAction SilentlyContinue) {
    & "knowledge-base"
} else {
    throw "knowledge-base command not found. Please run install script first."
}
'@

    $runBatScript = @"
@echo off
setlocal
cd /d "%~dp0"
set "KB_PROJECT_ROOT=%~dp0"

if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

if exist ".venv\Scripts\knowledge-base.exe" (
    ".venv\Scripts\knowledge-base.exe"
) else if exist ".venv\Scripts\knowledge-base" (
        ".venv\Scripts\knowledge-base"
) else (
        where knowledge-base >nul 2>nul
        if errorlevel 1 (
                echo [x] knowledge-base command not found. Please run install script first.
                exit /b 1
        )
        knowledge-base
)
endlocal
"@

        $installShScript = @'
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

select_python() {
    local candidates=()
    local cmd
    for cmd in python3.13 python3.12 python3.11 python3.10 python3.9 python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            local resolved
            resolved="$(command -v "$cmd")"
            local exists=0
            for item in "${candidates[@]:-}"; do
                if [[ "$item" == "$resolved" ]]; then
                    exists=1
                    break
                fi
            done
            if [[ $exists -eq 0 ]]; then
                candidates+=("$resolved")
            fi
        fi
    done

    if [[ ${#candidates[@]} -eq 0 ]]; then
        echo "[x] No Python interpreter found. Please install Python 3.12+ and retry." >&2
        exit 1
    fi

    # Filter to minimum version 3.12
    local qualified=()
    local exe
    for exe in "${candidates[@]}"; do
        local ver
        ver="$( "$exe" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true )"
        local major minor
        IFS='.' read -r major minor _ <<< "$ver"
        if [[ -n "$major" ]] && ((major > 3 || (major == 3 && minor >= 12))); then
            qualified+=("$exe")
        else
            echo "[!] Skipping $exe (Python $ver, requires >= 3.12)"
        fi
    done

    if [[ ${#qualified[@]} -eq 0 ]]; then
        echo "[x] No Python 3.12+ interpreter found. Please install Python 3.12 or higher and retry." >&2
        exit 1
    fi

    if [[ ${#qualified[@]} -eq 1 ]]; then
        echo "${qualified[0]}"
        return
    fi

    echo "[*] Multiple Python 3.12+ interpreters detected. Please choose one:"
    local i
    for i in "${!qualified[@]}"; do
        local ver
        ver="$( "${qualified[$i]}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null || true )"
        echo "[$((i + 1))] ${qualified[$i]}  (Python $ver)"
    done

    while true; do
        read -r -p "Enter number (1-${#qualified[@]}): " choice
        if [[ "$choice" =~ ^[0-9]+$ ]] && ((choice >= 1 && choice <= ${#qualified[@]})); then
            echo "${qualified[$((choice - 1))]}"
            return
        fi
        echo "[!] Invalid selection, please try again."
    done
}

PYTHON_CMD="$(select_python)"
echo "[*] Using Python: $PYTHON_CMD"

if [[ ! -d ".venv" ]]; then
    echo "[*] Creating virtual environment..."
    "$PYTHON_CMD" -m venv .venv
fi

if [[ -f ".venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

echo "[*] Installing dependencies..."
pip install -r requirements.txt

has_nvidia=0
has_amd=0
command -v nvidia-smi >/dev/null 2>&1 && has_nvidia=1 || true
command -v rocm-smi  >/dev/null 2>&1 && has_amd=1  || true

if [[ $has_nvidia -eq 1 ]]; then
    echo "[*] NVIDIA GPU detected, installing CUDA torch wheel (cu121)..."
    pip install --force-reinstall torch==2.2.2 --index-url https://download.pytorch.org/whl/cu121 || \
        echo "[!] CUDA torch install failed, keep current torch package"

    echo "[*] NVIDIA GPU detected, trying FAISS GPU package..."
    if ! pip install --force-reinstall faiss-gpu==1.8.0; then
        echo "[!] faiss-gpu install failed, fallback to faiss-cpu"
        pip install --force-reinstall faiss-cpu==1.8.0
    fi
elif [[ $has_amd -eq 1 ]]; then
    echo "[*] AMD GPU detected, installing ROCm torch wheel (rocm6.0)..."
    pip install --force-reinstall torch==2.2.2 --index-url https://download.pytorch.org/whl/rocm6.0 || \
        echo "[!] ROCm torch install failed, keep current torch package"
    echo "[!] faiss-gpu is not supported on AMD ROCm, using faiss-cpu"
    pip install --force-reinstall faiss-cpu==1.8.0
fi

wheel_file="$(ls -t ./*.whl 2>/dev/null | head -n 1 || true)"
if [[ -z "$wheel_file" ]]; then
    echo "[x] No wheel found in current directory"
    exit 1
fi

echo "[*] Installing wheel package: $(basename "$wheel_file")"
pip install --force-reinstall --no-deps "$wheel_file"

echo "[+] Install completed"
'@

        $runShScript = @'
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
export KB_PROJECT_ROOT="$SCRIPT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

if [[ -x ".venv/bin/knowledge-base" ]]; then
    .venv/bin/knowledge-base
elif command -v knowledge-base >/dev/null 2>&1; then
    knowledge-base
else
    echo "[x] knowledge-base command not found. Please run install script first."
    exit 1
fi
'@

    Set-Content -Path (Join-Path $Destination "install.ps1") -Value $installScript -Encoding UTF8
    Set-Content -Path (Join-Path $Destination "run.ps1") -Value $runPsScript -Encoding UTF8
    Set-Content -Path (Join-Path $Destination "run.bat") -Value $runBatScript -Encoding ASCII
        Set-Content -Path (Join-Path $Destination "install.sh") -Value $installShScript -Encoding UTF8
        Set-Content -Path (Join-Path $Destination "run.sh") -Value $runShScript -Encoding UTF8
}

function Stage-DeploymentBundle {
    param(
        [string]$Root,
                [string]$Destination,
                [string]$WheelPath
    )

        Write-Info "Staging scripts/config files into deployment bundle..."

        if (-not (Test-Path $Destination)) {
                New-Item -ItemType Directory -Path $Destination | Out-Null
        }

    $fileList = @(
        "config.json",
                "config.multi-provider.example.json",
        "requirements.txt",
                "README.md",
        "manage_service.ps1",
        "manage_service.bat",
        "uninstall.ps1",
        "uninstall.bat"
    )

    foreach ($file in $fileList) {
        $src = Join-Path $Root $file
        Copy-IfExists -Source $src -Destination $Destination
    }

    $dirList = @("web", "docs", "assets")
    foreach ($dir in $dirList) {
        $src = Join-Path $Root $dir
        Copy-IfExists -Source $src -Destination (Join-Path $Destination $dir) -IsDirectory
    }

    if (-not (Test-Path $WheelPath)) {
        throw "Wheel file not found: $WheelPath"
    }
    Copy-Item -Path $WheelPath -Destination $Destination -Force

    New-DeployScripts -Destination $Destination
    Write-Success "Deployment files staged in $Destination"
}

try {
    if (-not (Test-Path $PyprojectPath)) {
        throw "pyproject.toml not found: $PyprojectPath"
    }

    Write-Info "Project root: $ProjectRoot"
    Write-Info "Python executable: $PythonExe"

    if ($Clean) {
        Write-Info "Cleaning output directory..."
        if (Test-Path $OutputPath) {
            Get-ChildItem -Path $OutputPath -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    if (-not (Test-Path $OutputPath)) {
        New-Item -ItemType Directory -Path $OutputPath | Out-Null
    }

    Write-Info "Installing wheel build dependencies..."
    & $PythonExe -m pip install --upgrade pip setuptools wheel build
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install build dependencies"
    }

    Write-Info "Building wheel package..."
    & $PythonExe -m build --wheel --outdir $OutputPath
    if ($LASTEXITCODE -ne 0) {
        throw "Wheel build failed"
    }

    $wheelFiles = Get-ChildItem -Path $OutputPath -Filter "*.whl" | Sort-Object LastWriteTime -Descending
    if (-not $wheelFiles) {
        throw "Build completed but no .whl file found in $OutputPath"
    }

    $latestWheel = $wheelFiles[0].FullName
    $bundlePath = Join-Path $OutputPath $BundleName
    if (Test-Path $bundlePath) {
        Remove-Item -Path $bundlePath -Recurse -Force
    }

    Stage-DeploymentBundle -Root $ProjectRoot -Destination $bundlePath -WheelPath $latestWheel

    $archivePath = Join-Path $OutputPath ($BundleName + ".tar.gz")
    Write-Info "Creating tar.gz package..."
    New-TarGzArchive -SourceDirectory $bundlePath -ArchivePath $archivePath

    Write-Success "Wheel build completed"
    Write-Success "Deployment archive generated: $archivePath"
    Write-Host ""
    Write-Host "Generated wheel(s):" -ForegroundColor Cyan
    foreach ($f in $wheelFiles) {
        Write-Host "  - $($f.FullName)"
    }
    Write-Host ""
    Write-Host "Generated tar.gz:" -ForegroundColor Cyan
    Write-Host "  - $archivePath"
    Write-Host ""
    Write-Host "Install test command:" -ForegroundColor Cyan
    Write-Host "  $PythonExe -m pip install --force-reinstall $($wheelFiles[0].FullName)"
}
catch {
    Write-Error-Custom $_
    exit 1
}
