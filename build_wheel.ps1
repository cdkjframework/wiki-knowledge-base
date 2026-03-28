param(
    [switch]$Clean = $true,
    [string]$OutputDir = "./dist",
    [string]$BundleName = "knowledge-base-deploy",
    [switch]$BuildCustomFaissGpuWheel = $false,
    [string]$CustomFaissWheelPath = "",
    [ValidateSet("CUDA", "ROCM", "CUVS")]
    [string]$FaissGpuSupport = "CUDA",
    [string]$FaissOptLevels = "generic,avx2",
    [string]$FaissWheelOutputDir = "./dist/faiss-gpu-wheel",
    [string]$FaissWheelWorkspace = "./build/faiss-wheels-src",
    [string]$FaissWheelRepoRef = "main"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$OutputPath = Join-Path $ProjectRoot $OutputDir
$PyprojectPath = Join-Path $ProjectRoot "pyproject.toml"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PythonExe = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

function Resolve-ProjectPath {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $null
    }

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return $Path
    }

    return Join-Path $ProjectRoot $Path
}

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

function Resolve-BundleFaissWheelPath {
    param([string]$WheelPath)

    if ([string]::IsNullOrWhiteSpace($WheelPath)) {
        return $null
    }

    $resolvedPath = Resolve-ProjectPath $WheelPath
    if (-not (Test-Path $resolvedPath)) {
        throw "Custom FAISS wheel not found: $resolvedPath"
    }

    return (Resolve-Path $resolvedPath).Path
}

function Invoke-CustomFaissWheelBuild {
    param(
        [string]$GpuSupport,
        [string]$OptLevels,
        [string]$WheelOutputDir,
        [string]$WheelWorkspace,
        [string]$RepoRef
    )

    $builderScript = Join-Path $ProjectRoot "build_faiss_gpu_wheel.ps1"
    if (-not (Test-Path $builderScript)) {
        throw "Custom FAISS wheel builder script not found: $builderScript"
    }

    $resolvedOutputDir = Resolve-ProjectPath $WheelOutputDir
    $resolvedWorkspace = Resolve-ProjectPath $WheelWorkspace

    Write-Info "Building custom FAISS GPU wheel..."
    $builderOutput = & $builderScript `
        -GpuSupport $GpuSupport `
        -FaissOptLevels $OptLevels `
        -OutputDir $resolvedOutputDir `
        -WorkDir $resolvedWorkspace `
        -RepoRef $RepoRef `
        -PythonExe $PythonExe

    if ($LASTEXITCODE -ne 0) {
        throw "Custom FAISS GPU wheel build failed"
    }

    $wheelPath = ($builderOutput | Select-Object -Last 1)
    if ([string]::IsNullOrWhiteSpace($wheelPath) -or -not (Test-Path $wheelPath)) {
        throw "Custom FAISS GPU wheel build completed but no wheel path was returned"
    }

    return (Resolve-Path $wheelPath).Path
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

function Normalize-RequirementsEncoding {
    param([string]$Root)

    $files = @(
        "requirements.txt",
        "requirements.build.txt",
        "requirements.optional-parser.txt"
    )

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    foreach ($file in $files) {
        $path = Join-Path $Root $file
        if (-not (Test-Path $path)) {
            continue
        }

        $content = Get-Content -Raw -LiteralPath $path
        [System.IO.File]::WriteAllText($path, $content, $utf8NoBom)
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
    param(
        [string]$Destination,
        [switch]$IncludeBundledFaissWheel
    )

    $installScript = @'
param(
    [switch]$SkipVenv = $false,
        [switch]$SkipCudaTorch = $false,
        [switch]$ForceCustomFaissWheel = $false,
        [string]$CustomFaissWheel = ""
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

function Resolve-CustomFaissWheel {
    param(
        [string]$BasePath,
        [string]$WheelPath,
        [switch]$ForceAutoDetect
    )

    if (-not [string]::IsNullOrWhiteSpace($WheelPath)) {
        $resolvedPath = if ([System.IO.Path]::IsPathRooted($WheelPath)) {
            $WheelPath
        } else {
            Join-Path $BasePath $WheelPath
        }

        if (-not (Test-Path $resolvedPath)) {
            throw "Custom FAISS wheel not found: $resolvedPath"
        }

        return (Resolve-Path $resolvedPath).Path
    }

    if ($ForceAutoDetect) {
        $candidate = Get-ChildItem -Path $BasePath -Filter "faiss*.whl" -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if (-not $candidate) {
            throw "ForceCustomFaissWheel was set but no faiss*.whl was found in $BasePath. Use -CustomFaissWheel to specify the wheel path."
        }

        return $candidate.FullName
    }

    return $null
}

function Install-FaissPackage {
    param(
        [string]$BasePath,
        [string]$WheelPath,
        [switch]$ForceAutoDetect
    )

    $customWheel = Resolve-CustomFaissWheel -BasePath $BasePath -WheelPath $WheelPath -ForceAutoDetect:$ForceAutoDetect
    if ($customWheel) {
        Write-Host "[*] Installing custom FAISS wheel: $customWheel" -ForegroundColor Cyan
        pip install --force-reinstall --no-deps $customWheel
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install custom FAISS wheel: $customWheel"
        }
        return
    }

    Write-Host "[*] Ensuring faiss-cpu==1.8.0 is installed..." -ForegroundColor Cyan
    pip install --force-reinstall faiss-cpu==1.8.0
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install faiss-cpu"
    }
}

function Ensure-NumpyCompat {
    Write-Host "[*] Enforcing NumPy compatibility (numpy==1.26.4)..." -ForegroundColor Cyan
    pip install --force-reinstall --no-deps numpy==1.26.4
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install numpy==1.26.4"
    }
}

function Get-RequirementPinnedVersion {
    param(
        [string]$FilePath,
        [string]$PackageName
    )

    if (-not (Test-Path $FilePath)) {
        return $null
    }

    $pattern = "^(?i)" + [regex]::Escape($PackageName) + "\s*==\s*([^\s;#]+)"
    foreach ($line in Get-Content $FilePath) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith("#")) {
            continue
        }

        $trimmed = $trimmed -replace "\s+#.*$", ""
        $m = [regex]::Match($trimmed, $pattern)
        if ($m.Success) {
            return $m.Groups[1].Value
        }
    }

    return $null
}

function Get-InstalledPackageVersion {
    param(
        [string]$PythonCmd,
        [string]$PackageName
    )

    try {
        $ver = & $PythonCmd -c "import importlib.metadata as m; print(m.version('$PackageName'))" 2>$null
        if (-not [string]::IsNullOrWhiteSpace($ver)) {
            return $ver.Trim()
        }
    } catch {}

    return $null
}

function Add-LocalVersionSuffix {
    param(
        [string]$Version,
        [string]$Suffix
    )

    if ([string]::IsNullOrWhiteSpace($Version)) {
        return $null
    }

    if ($Version -match "\+") {
        return $Version
    }

    return "$Version+$Suffix"
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
if (Test-Path Env:PIP_REQUIRE_HASHES) {
    Write-Host "[*] Clearing PIP_REQUIRE_HASHES for dependency install..." -ForegroundColor Yellow
    Remove-Item Env:PIP_REQUIRE_HASHES -ErrorAction SilentlyContinue
}
pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    throw "pip install -r requirements.txt failed"
}

$requirementsPath = Join-Path $ScriptPath "requirements.txt"
$torchVersion = Get-RequirementPinnedVersion -FilePath $requirementsPath -PackageName "torch"
$torchvisionVersion = Get-RequirementPinnedVersion -FilePath $requirementsPath -PackageName "torchvision"

if (-not $torchVersion) {
    $torchVersion = Get-InstalledPackageVersion -PythonCmd $PythonCmd -PackageName "torch"
    if ($torchVersion) {
        Write-Host "[!] torch pin not found in requirements.txt; using installed torch $torchVersion" -ForegroundColor Yellow
    } else {
        Write-Host "[!] torch pin not found in requirements.txt; skipping CUDA/ROCm torch override" -ForegroundColor Yellow
    }
}

if (-not $torchvisionVersion) {
    $torchvisionVersion = Get-InstalledPackageVersion -PythonCmd $PythonCmd -PackageName "torchvision"
    if ($torchvisionVersion) {
        Write-Host "[!] torchvision pin not found in requirements.txt; using installed torchvision $torchvisionVersion" -ForegroundColor Yellow
    } else {
        Write-Host "[!] torchvision pin not found in requirements.txt; CUDA/ROCm torchvision override may be skipped" -ForegroundColor Yellow
    }
}

$cudaTorchVersion = Add-LocalVersionSuffix -Version $torchVersion -Suffix "cu121"
$cudaTorchvisionVersion = Add-LocalVersionSuffix -Version $torchvisionVersion -Suffix "cu121"
$rocmTorchVersion = Add-LocalVersionSuffix -Version $torchVersion -Suffix "rocm6.0"
$rocmTorchvisionVersion = Add-LocalVersionSuffix -Version $torchvisionVersion -Suffix "rocm6.0"

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
        if ($cudaTorchVersion) {
            Write-Host "[*] NVIDIA GPU detected, installing CUDA torch wheel (cu121) for torch==$cudaTorchVersion..." -ForegroundColor Cyan
            pip install --force-reinstall --no-deps torch==$cudaTorchVersion --index-url https://download.pytorch.org/whl/cu121
            if ($LASTEXITCODE -ne 0) {
                Write-Host "[!] CUDA torch install failed, keep current torch package" -ForegroundColor Yellow
            }
        } else {
            Write-Host "[!] torch version not resolved; skipping CUDA torch override" -ForegroundColor Yellow
        }

        if ($cudaTorchvisionVersion) {
            Write-Host "[*] Installing CUDA torchvision wheel (cu121) for torchvision==$cudaTorchvisionVersion..." -ForegroundColor Cyan
            pip install --force-reinstall --no-deps torchvision==$cudaTorchvisionVersion --index-url https://download.pytorch.org/whl/cu121
            if ($LASTEXITCODE -ne 0) {
                Write-Host "[!] CUDA torchvision install failed, keep current torchvision package" -ForegroundColor Yellow
            }
        } else {
            Write-Host "[!] torchvision version not resolved; skipping CUDA torchvision override" -ForegroundColor Yellow
        }

        if (-not $ForceCustomFaissWheel -and [string]::IsNullOrWhiteSpace($CustomFaissWheel)) {
            Write-Host "[!] PyPI does not provide a matching faiss-gpu wheel here; use -CustomFaissWheel or -ForceCustomFaissWheel to install a local GPU build." -ForegroundColor Yellow
        }
    } elseif ($hasAmd) {
        if ($rocmTorchVersion) {
            Write-Host "[*] AMD GPU detected, installing ROCm torch wheel (rocm6.0) for torch==$rocmTorchVersion..." -ForegroundColor Cyan
            pip install --force-reinstall --no-deps torch==$rocmTorchVersion --index-url https://download.pytorch.org/whl/rocm6.0
            if ($LASTEXITCODE -ne 0) {
                Write-Host "[!] ROCm torch install failed, keep current torch package" -ForegroundColor Yellow
            }
        } else {
            Write-Host "[!] torch version not resolved; skipping ROCm torch override" -ForegroundColor Yellow
        }

        if ($rocmTorchvisionVersion) {
            Write-Host "[*] Installing ROCm torchvision wheel (rocm6.0) for torchvision==$rocmTorchvisionVersion..." -ForegroundColor Cyan
            pip install --force-reinstall --no-deps torchvision==$rocmTorchvisionVersion --index-url https://download.pytorch.org/whl/rocm6.0
            if ($LASTEXITCODE -ne 0) {
                Write-Host "[!] ROCm torchvision install failed, keep current torchvision package" -ForegroundColor Yellow
            }
        } else {
            Write-Host "[!] torchvision version not resolved; skipping ROCm torchvision override" -ForegroundColor Yellow
        }

        if (-not $ForceCustomFaissWheel -and [string]::IsNullOrWhiteSpace($CustomFaissWheel)) {
            Write-Host "[!] No custom ROCm FAISS wheel was provided, using faiss-cpu" -ForegroundColor Yellow
        }
    }
}

Install-FaissPackage -BasePath $ScriptPath -WheelPath $CustomFaissWheel -ForceAutoDetect:$ForceCustomFaissWheel
Ensure-NumpyCompat

$wheel = Get-ChildItem -Path $ScriptPath -Filter "knowledge_base-*.whl" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($wheel) {
    Write-Host "[*] Installing wheel package: $($wheel.Name)" -ForegroundColor Cyan
    pip install --force-reinstall --no-deps $wheel.FullName
    if ($LASTEXITCODE -ne 0) {
        throw "pip install wheel failed"
    }
} else {
    throw "No knowledge_base wheel found in current directory"
}

Write-Host "[+] Install completed" -ForegroundColor Green
'@

    $installGpuPsScript = @'
param(
    [switch]$SkipVenv = $false,
    [switch]$SkipCudaTorch = $false,
    [string]$CustomFaissWheel = ""
)

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$installScriptPath = Join-Path $ScriptPath "install.ps1"

if (-not (Test-Path $installScriptPath)) {
    throw "install.ps1 not found: $installScriptPath"
}

$invokeArgs = @{}
if ($SkipVenv) {
    $invokeArgs.SkipVenv = $true
}
if ($SkipCudaTorch) {
    $invokeArgs.SkipCudaTorch = $true
}
if ([string]::IsNullOrWhiteSpace($CustomFaissWheel)) {
    $invokeArgs.ForceCustomFaissWheel = $true
} else {
    $invokeArgs.CustomFaissWheel = $CustomFaissWheel
}

& $installScriptPath @invokeArgs
'@

    $installGpuBatScript = @"
@echo off
setlocal
set "SCRIPT_DIR=%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%install.ps1" -ForceCustomFaissWheel %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo [x] GPU-aware install failed with exit code %EXIT_CODE%
) else (
    echo [+] GPU-aware install completed
)

exit /b %EXIT_CODE%
"@

    $runPsScript = @'
param(
    [ValidateSet("run", "service-install", "service-start", "service-install-start", "service-stop", "service-restart", "service-status", "service-uninstall")]
    [string]$Command = "run"
)

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptPath
$env:KB_PROJECT_ROOT = $ScriptPath

if ($Command -ne "run") {
    $isWindows = ($env:OS -eq "Windows_NT")
    $serviceMap = @{
        "service-install" = "install"
        "service-start" = "start"
        "service-stop" = "stop"
        "service-restart" = "restart"
        "service-status" = "status"
        "service-uninstall" = "uninstall"
    }

    if ($isWindows) {
        $manager = Join-Path $ScriptPath "manage_service.ps1"
        if (-not (Test-Path $manager)) {
            throw "manage_service.ps1 not found in $ScriptPath"
        }

        if ($Command -eq "service-install-start") {
            & $manager -Command install
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            & $manager -Command start
            exit $LASTEXITCODE
        }

        & $manager -Command $serviceMap[$Command]
        exit $LASTEXITCODE
    }

    $managerSh = Join-Path $ScriptPath "manage_service.sh"
    if (-not (Test-Path $managerSh)) {
        throw "manage_service.sh not found in $ScriptPath"
    }

    $bashCmd = Get-Command "bash" -ErrorAction SilentlyContinue
    if (-not $bashCmd) {
        throw "bash command not found. Please run manage_service.sh manually on Linux."
    }

    if ($Command -eq "service-install-start") {
        & $bashCmd.Source $managerSh install
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $bashCmd.Source $managerSh start
        exit $LASTEXITCODE
    }

    & $bashCmd.Source $managerSh $serviceMap[$Command]
    exit $LASTEXITCODE
}

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

if /i "%~1"=="service-install" (
    call ".\manage_service.bat" install
    exit /b %errorlevel%
)
if /i "%~1"=="service-start" (
    call ".\manage_service.bat" start
    exit /b %errorlevel%
)
if /i "%~1"=="service-install-start" (
    call ".\manage_service.bat" install
    if errorlevel 1 exit /b %errorlevel%
    call ".\manage_service.bat" start
    exit /b %errorlevel%
)
if /i "%~1"=="service-stop" (
    call ".\manage_service.bat" stop
    exit /b %errorlevel%
)
if /i "%~1"=="service-restart" (
    call ".\manage_service.bat" restart
    exit /b %errorlevel%
)
if /i "%~1"=="service-status" (
    call ".\manage_service.bat" status
    exit /b %errorlevel%
)
if /i "%~1"=="service-uninstall" (
    call ".\manage_service.bat" uninstall
    exit /b %errorlevel%
)

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

SKIP_VENV=0
SKIP_CUDA_TORCH=0
FORCE_CUSTOM_FAISS_WHEEL=0
CUSTOM_FAISS_WHEEL=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-venv)
            SKIP_VENV=1
            ;;
        --skip-cuda-torch)
            SKIP_CUDA_TORCH=1
            ;;
        --force-custom-faiss-wheel)
            FORCE_CUSTOM_FAISS_WHEEL=1
            ;;
        --custom-faiss-wheel)
            shift
            if [[ $# -eq 0 ]]; then
                echo "[x] --custom-faiss-wheel requires a wheel path" >&2
                exit 1
            fi
            CUSTOM_FAISS_WHEEL="$1"
            ;;
        *)
            echo "[x] Unknown argument: $1" >&2
            exit 1
            ;;
    esac
    shift
done

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

resolve_custom_faiss_wheel() {
    if [[ -n "$CUSTOM_FAISS_WHEEL" ]]; then
        local candidate
        if [[ "$CUSTOM_FAISS_WHEEL" = /* ]]; then
            candidate="$CUSTOM_FAISS_WHEEL"
        else
            candidate="$SCRIPT_DIR/$CUSTOM_FAISS_WHEEL"
        fi

        if [[ ! -f "$candidate" ]]; then
            echo "[x] Custom FAISS wheel not found: $candidate" >&2
            exit 1
        fi

        printf '%s\n' "$candidate"
        return
    fi

    if [[ $FORCE_CUSTOM_FAISS_WHEEL -eq 1 ]]; then
        local candidate
        candidate="$(find "$SCRIPT_DIR" -maxdepth 1 -type f -name 'faiss*.whl' | head -n 1 || true)"
        if [[ -z "$candidate" ]]; then
            echo "[x] --force-custom-faiss-wheel was set but no faiss*.whl was found in $SCRIPT_DIR" >&2
            exit 1
        fi

        printf '%s\n' "$candidate"
    fi
}

install_faiss_package() {
    local custom_wheel
    custom_wheel="$(resolve_custom_faiss_wheel)"
    if [[ -n "$custom_wheel" ]]; then
        echo "[*] Installing custom FAISS wheel: $custom_wheel"
        pip install --force-reinstall --no-deps "$custom_wheel"
        return
    fi

    echo "[*] Ensuring faiss-cpu==1.8.0 is installed..."
    pip install --force-reinstall --no-deps faiss-cpu==1.8.0
}

ensure_numpy_compat() {
    echo "[*] Enforcing NumPy compatibility (numpy==1.26.4)..."
    pip install --force-reinstall --no-deps numpy==1.26.4
}

PYTHON_CMD="$(select_python)"
echo "[*] Using Python: $PYTHON_CMD"

if [[ ! -d ".venv" && $SKIP_VENV -eq 0 ]]; then
    echo "[*] Creating virtual environment..."
    "$PYTHON_CMD" -m venv .venv
fi

if [[ -f ".venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

echo "[*] Installing dependencies..."
unset PIP_REQUIRE_HASHES || true
pip install -r requirements.txt

get_requirement_version() {
    local name="$1"
    local file="$2"
    [[ -f "$file" ]] || return 1
    local line
    line="$(grep -i -E "^[[:space:]]*${name}[[:space:]]*==[[:space:]]*[^#;[:space:]]+" "$file" | head -n 1 || true)"
    [[ -z "$line" ]] && return 1
    line="${line%%#*}"
    line="${line%%;*}"
    echo "$line" | sed -E "s/^[[:space:]]*${name}[[:space:]]*==[[:space:]]*//I"
}

get_installed_version() {
    local name="$1"
    "$PYTHON_CMD" -c "import importlib.metadata as m; print(m.version('$name'))" 2>/dev/null || true
}

add_local_version() {
    local version="$1"
    local suffix="$2"
    [[ -z "$version" ]] && return 1
    if [[ "$version" == *"+"* ]]; then
        echo "$version"
        return 0
    fi
    echo "${version}+${suffix}"
}

torch_version="$(get_requirement_version torch "$SCRIPT_DIR/requirements.txt" || true)"
torchvision_version="$(get_requirement_version torchvision "$SCRIPT_DIR/requirements.txt" || true)"
if [[ -z "$torch_version" ]]; then
    torch_version="$(get_installed_version torch)"
    if [[ -n "$torch_version" ]]; then
        echo "[!] torch pin not found in requirements.txt; using installed torch $torch_version"
    else
        echo "[!] torch pin not found in requirements.txt; skipping CUDA/ROCm torch override"
    fi
fi

if [[ -z "$torchvision_version" ]]; then
    torchvision_version="$(get_installed_version torchvision)"
    if [[ -n "$torchvision_version" ]]; then
        echo "[!] torchvision pin not found in requirements.txt; using installed torchvision $torchvision_version"
    else
        echo "[!] torchvision pin not found in requirements.txt; CUDA/ROCm torchvision override may be skipped"
    fi
fi

cuda_torch_version="$(add_local_version "$torch_version" "cu121" || true)"
cuda_torchvision_version="$(add_local_version "$torchvision_version" "cu121" || true)"
rocm_torch_version="$(add_local_version "$torch_version" "rocm6.0" || true)"
rocm_torchvision_version="$(add_local_version "$torchvision_version" "rocm6.0" || true)"

has_nvidia=0
has_amd=0
command -v nvidia-smi >/dev/null 2>&1 && has_nvidia=1 || true
command -v rocm-smi  >/dev/null 2>&1 && has_amd=1  || true

if [[ $SKIP_CUDA_TORCH -eq 0 ]]; then
    if [[ $has_nvidia -eq 1 ]]; then
        if [[ -n "$cuda_torch_version" ]]; then
            echo "[*] NVIDIA GPU detected, installing CUDA torch wheel (cu121) for torch==$cuda_torch_version..."
            pip install --force-reinstall --no-deps "torch==${cuda_torch_version}" --index-url https://download.pytorch.org/whl/cu121 || \
                echo "[!] CUDA torch install failed, keep current torch package"
        else
            echo "[!] torch version not resolved; skipping CUDA torch override"
        fi

        if [[ -n "$cuda_torchvision_version" ]]; then
            echo "[*] Installing CUDA torchvision wheel (cu121) for torchvision==$cuda_torchvision_version..."
            pip install --force-reinstall --no-deps "torchvision==${cuda_torchvision_version}" --index-url https://download.pytorch.org/whl/cu121 || \
                echo "[!] CUDA torchvision install failed, keep current torchvision package"
        else
            echo "[!] torchvision version not resolved; skipping CUDA torchvision override"
        fi

        if [[ $FORCE_CUSTOM_FAISS_WHEEL -eq 0 && -z "$CUSTOM_FAISS_WHEEL" ]]; then
            echo "[!] PyPI does not provide a matching faiss-gpu wheel here; use --custom-faiss-wheel or --force-custom-faiss-wheel to install a local GPU build."
        fi
    elif [[ $has_amd -eq 1 ]]; then
        if [[ -n "$rocm_torch_version" ]]; then
            echo "[*] AMD GPU detected, installing ROCm torch wheel (rocm6.0) for torch==$rocm_torch_version..."
            pip install --force-reinstall --no-deps "torch==${rocm_torch_version}" --index-url https://download.pytorch.org/whl/rocm6.0 || \
                echo "[!] ROCm torch install failed, keep current torch package"
        else
            echo "[!] torch version not resolved; skipping ROCm torch override"
        fi

        if [[ -n "$rocm_torchvision_version" ]]; then
            echo "[*] Installing ROCm torchvision wheel (rocm6.0) for torchvision==$rocm_torchvision_version..."
            pip install --force-reinstall --no-deps "torchvision==${rocm_torchvision_version}" --index-url https://download.pytorch.org/whl/rocm6.0 || \
                echo "[!] ROCm torchvision install failed, keep current torchvision package"
        else
            echo "[!] torchvision version not resolved; skipping ROCm torchvision override"
        fi

        if [[ $FORCE_CUSTOM_FAISS_WHEEL -eq 0 && -z "$CUSTOM_FAISS_WHEEL" ]]; then
            echo "[!] No custom ROCm FAISS wheel was provided, using faiss-cpu"
        fi
    fi
fi

install_faiss_package
ensure_numpy_compat

wheel_file="$(ls -t ./knowledge_base-*.whl 2>/dev/null | head -n 1 || true)"
if [[ -z "$wheel_file" ]]; then
    echo "[x] No knowledge_base wheel found in current directory"
    exit 1
fi

echo "[*] Installing wheel package: $(basename "$wheel_file")"
pip install --force-reinstall --no-deps "$wheel_file"

echo "[+] Install completed"
'@

    $installGpuShScript = @'
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

exec "$SCRIPT_DIR/install.sh" --force-custom-faiss-wheel "$@"
'@

        $runShScript = @'
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
export KB_PROJECT_ROOT="$SCRIPT_DIR"

COMMAND="${1:-run}"
if [[ "$COMMAND" != "run" ]]; then
    if [[ ! -f "$SCRIPT_DIR/manage_service.sh" ]]; then
        echo "[x] manage_service.sh not found in $SCRIPT_DIR" >&2
        exit 1
    fi

    case "$COMMAND" in
        service-install)
            bash "$SCRIPT_DIR/manage_service.sh" install
            ;;
        service-start)
            bash "$SCRIPT_DIR/manage_service.sh" start
            ;;
        service-install-start)
            bash "$SCRIPT_DIR/manage_service.sh" install
            bash "$SCRIPT_DIR/manage_service.sh" start
            ;;
        service-stop)
            bash "$SCRIPT_DIR/manage_service.sh" stop
            ;;
        service-restart)
            bash "$SCRIPT_DIR/manage_service.sh" restart
            ;;
        service-status)
            bash "$SCRIPT_DIR/manage_service.sh" status
            ;;
        service-uninstall)
            bash "$SCRIPT_DIR/manage_service.sh" uninstall
            ;;
        *)
            echo "[x] Unknown command: $COMMAND" >&2
            exit 1
            ;;
    esac
    exit 0
fi

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
    if ($IncludeBundledFaissWheel) {
        Set-Content -Path (Join-Path $Destination "install-gpu.ps1") -Value $installGpuPsScript -Encoding UTF8
        Set-Content -Path (Join-Path $Destination "install-gpu.bat") -Value $installGpuBatScript -Encoding ASCII
        Set-Content -Path (Join-Path $Destination "install-gpu.sh") -Value $installGpuShScript -Encoding UTF8
    }
    Set-Content -Path (Join-Path $Destination "install.sh") -Value $installShScript -Encoding UTF8
    Set-Content -Path (Join-Path $Destination "run.sh") -Value $runShScript -Encoding UTF8
}

function Stage-DeploymentBundle {
    param(
        [string]$Root,
        [string]$Destination,
        [string]$WheelPath,
        [string]$FaissWheelPath
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
        "manage_service.sh",
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

    if (-not [string]::IsNullOrWhiteSpace($FaissWheelPath)) {
        if (-not (Test-Path $FaissWheelPath)) {
            throw "Custom FAISS wheel file not found: $FaissWheelPath"
        }
        Copy-Item -Path $FaissWheelPath -Destination $Destination -Force
    }

    New-DeployScripts -Destination $Destination -IncludeBundledFaissWheel:(-not [string]::IsNullOrWhiteSpace($FaissWheelPath))
    Write-Success "Deployment files staged in $Destination"
}

try {
    if (-not (Test-Path $PyprojectPath)) {
        throw "pyproject.toml not found: $PyprojectPath"
    }

    if ($BuildCustomFaissGpuWheel -and -not [string]::IsNullOrWhiteSpace($CustomFaissWheelPath)) {
        throw "Use either -BuildCustomFaissGpuWheel or -CustomFaissWheelPath, not both."
    }

    Write-Info "Project root: $ProjectRoot"
    Write-Info "Python executable: $PythonExe"
    Write-Info "Normalizing requirements encoding (UTF-8 without BOM)..."
    Normalize-RequirementsEncoding -Root $ProjectRoot

    if ($Clean) {
        Write-Info "Cleaning output directory..."
        if (Test-Path $OutputPath) {
            Get-ChildItem -Path $OutputPath -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    if (-not (Test-Path $OutputPath)) {
        New-Item -ItemType Directory -Path $OutputPath | Out-Null
    }

    $bundleFaissWheelPath = $null
    if ($BuildCustomFaissGpuWheel) {
        $bundleFaissWheelPath = Invoke-CustomFaissWheelBuild `
            -GpuSupport $FaissGpuSupport `
            -OptLevels $FaissOptLevels `
            -WheelOutputDir $FaissWheelOutputDir `
            -WheelWorkspace $FaissWheelWorkspace `
            -RepoRef $FaissWheelRepoRef
        Write-Success "Custom FAISS GPU wheel ready: $bundleFaissWheelPath"
    } elseif (-not [string]::IsNullOrWhiteSpace($CustomFaissWheelPath)) {
        $bundleFaissWheelPath = Resolve-BundleFaissWheelPath -WheelPath $CustomFaissWheelPath
        Write-Success "Using provided custom FAISS wheel: $bundleFaissWheelPath"
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

    $wheelFiles = Get-ChildItem -Path $OutputPath -Filter "knowledge_base-*.whl" | Sort-Object LastWriteTime -Descending
    if (-not $wheelFiles) {
        throw "Build completed but no knowledge_base wheel file was found in $OutputPath"
    }

    $latestWheel = $wheelFiles[0].FullName
    $bundlePath = Join-Path $OutputPath $BundleName
    if (Test-Path $bundlePath) {
        Remove-Item -Path $bundlePath -Recurse -Force
    }

    Stage-DeploymentBundle -Root $ProjectRoot -Destination $bundlePath -WheelPath $latestWheel -FaissWheelPath $bundleFaissWheelPath

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
    if ($bundleFaissWheelPath) {
        Write-Host ""
        Write-Host "Bundled custom FAISS wheel:" -ForegroundColor Cyan
        Write-Host "  - $bundleFaissWheelPath"
        Write-Host ""
        Write-Host "GPU deployment install command:" -ForegroundColor Cyan
        Write-Host "  .\install-gpu.ps1"
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
