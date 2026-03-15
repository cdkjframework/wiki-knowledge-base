param(
    [ValidateSet("CUDA", "ROCM", "CUVS")]
    [string]$GpuSupport = "CUDA",
    [string]$OutputDir = "./dist/faiss-gpu-wheel",
    [string]$WorkDir = "./build/faiss-wheels-src",
    [string]$RepoUrl = "https://github.com/kyamagu/faiss-wheels.git",
    [string]$RepoRef = "main",
    [string]$FaissOptLevels = "generic,avx2",
    [string]$PackageName = "faiss-gpu",
    [string]$PythonExe = "",
    [switch]$AutoInstallCMake = $false,
    [switch]$Clean = $false
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
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

function Test-RequiredCommand {
    param(
        [string]$Name,
        [string]$FailureMessage
    )

    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw $FailureMessage
    }
}

function Ensure-CMake {
    param([switch]$AutoInstall)

    $cmakeCmd = Get-Command "cmake" -ErrorAction SilentlyContinue
    if ($cmakeCmd) {
        return
    }

    $installHint = "cmake command not found. Please install CMake first. Quick fix: winget install -e --id Kitware.CMake --accept-package-agreements --accept-source-agreements"
    if (-not $AutoInstall) {
        throw $installHint
    }

    $wingetCmd = Get-Command "winget" -ErrorAction SilentlyContinue
    if (-not $wingetCmd) {
        throw "$installHint`nAuto install was requested, but winget is not available."
    }

    Write-Info "cmake not found, trying to install via winget..."
    & winget install -e --id Kitware.CMake --accept-package-agreements --accept-source-agreements --silent
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install CMake via winget. Please install CMake manually and retry."
    }

    $cmakeBin = "C:\Program Files\CMake\bin"
    if ((Test-Path $cmakeBin) -and (-not ($env:Path -split ';' | Where-Object { $_ -eq $cmakeBin }))) {
        $env:Path += ";$cmakeBin"
    }

    $cmakeCmd = Get-Command "cmake" -ErrorAction SilentlyContinue
    if (-not $cmakeCmd) {
        throw "CMake was installed but is still not available in PATH for current shell. Reopen terminal and retry."
    }

    Write-Success "CMake is available: $($cmakeCmd.Source)"
}

function Update-PyprojectPackageName {
    param(
        [string]$PyprojectPath,
        [string]$NewName
    )

    $content = Get-Content -Path $PyprojectPath -Raw
    $updated = [regex]::Replace($content, '(?m)^name = ".*"\s*$', "name = `"$NewName`"", 1)
    if ($updated -eq $content) {
        throw "Failed to update package name in $PyprojectPath"
    }

    Set-Content -Path $PyprojectPath -Value $updated -Encoding UTF8
}

$ResolvedOutputDir = Resolve-ProjectPath $OutputDir
$ResolvedWorkDir = Resolve-ProjectPath $WorkDir
$ResolvedPythonExe = if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    if (Test-Path $VenvPython) { $VenvPython } else { "python" }
} else {
    Resolve-ProjectPath $PythonExe
}

Write-Info "Project root: $ProjectRoot"
Write-Info "Python executable: $ResolvedPythonExe"
Write-Info "FAISS GPU support: $GpuSupport"
Write-Info "FAISS opt levels: $FaissOptLevels"

Test-RequiredCommand -Name "git" -FailureMessage "git command not found. Please install Git first."
Ensure-CMake -AutoInstall:$AutoInstallCMake

if ($GpuSupport -eq "CUDA") {
    if (-not (Get-Command "nvcc" -ErrorAction SilentlyContinue) -and -not $env:CUDA_PATH) {
        throw "CUDA toolkit not detected. Please install CUDA and ensure nvcc or CUDA_PATH is available."
    }
} elseif ($GpuSupport -eq "ROCM") {
    if (-not (Get-Command "hipcc" -ErrorAction SilentlyContinue) -and -not $env:ROCM_PATH) {
        throw "ROCm toolkit not detected. Please install ROCm and ensure hipcc or ROCM_PATH is available."
    }
}

if (-not (Get-Command "cl" -ErrorAction SilentlyContinue) -and -not $env:VSINSTALLDIR) {
    Write-Warning-Custom "MSVC compiler was not detected in the current shell. If the build fails, rerun from a Developer PowerShell for Visual Studio or initialize Build Tools first."
}

if ($Clean) {
    Write-Info "Cleaning FAISS wheel output/work directories..."
    foreach ($path in @($ResolvedOutputDir, $ResolvedWorkDir)) {
        if ($path -and (Test-Path $path)) {
            Remove-Item -Path $path -Recurse -Force
        }
    }
}

if (-not (Test-Path $ResolvedOutputDir)) {
    New-Item -ItemType Directory -Path $ResolvedOutputDir -Force | Out-Null
}

if (-not (Test-Path $ResolvedWorkDir)) {
    Write-Info "Cloning faiss-wheels repository..."
    & git clone --recursive $RepoUrl $ResolvedWorkDir
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to clone $RepoUrl"
    }
}

Write-Info "Installing build frontend..."
& $ResolvedPythonExe -m pip install --upgrade pip build
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install Python build frontend"
}

$previousGpuSupport = $env:FAISS_GPU_SUPPORT
$previousOptLevels = $env:FAISS_OPT_LEVELS

Push-Location $ResolvedWorkDir
try {
    Write-Info "Updating faiss-wheels repository..."
    & git fetch --tags origin
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to fetch faiss-wheels refs"
    }

    & git checkout $RepoRef
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to checkout faiss-wheels ref: $RepoRef"
    }

    & git submodule update --init --recursive
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to update faiss-wheels submodules"
    }

    Update-PyprojectPackageName -PyprojectPath (Join-Path $ResolvedWorkDir "pyproject.toml") -NewName $PackageName

    $env:FAISS_GPU_SUPPORT = $GpuSupport
    $env:FAISS_OPT_LEVELS = $FaissOptLevels

    Write-Info "Building custom FAISS wheel..."
    & $ResolvedPythonExe -m build --wheel --outdir $ResolvedOutputDir
    if ($LASTEXITCODE -ne 0) {
        throw "Custom FAISS wheel build failed"
    }
}
finally {
    $env:FAISS_GPU_SUPPORT = $previousGpuSupport
    $env:FAISS_OPT_LEVELS = $previousOptLevels
    Pop-Location
}

$wheelPrefix = $PackageName -replace '-', '_'
$latestWheel = Get-ChildItem -Path $ResolvedOutputDir -Filter "$wheelPrefix-*.whl" -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $latestWheel) {
    $latestWheel = Get-ChildItem -Path $ResolvedOutputDir -Filter "*.whl" -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1
}

if (-not $latestWheel) {
    throw "Build completed but no wheel file was found in $ResolvedOutputDir"
}

Write-Success "Custom FAISS wheel built: $($latestWheel.FullName)"
Write-Host ""
Write-Host "Install example:" -ForegroundColor Cyan
Write-Host "  pip install --force-reinstall --no-deps $($latestWheel.FullName)"

Write-Output $latestWheel.FullName