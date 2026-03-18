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
    [switch]$AutoInstallMsvc = $false,
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
        Write-Warning-Custom "winget install returned non-zero exit code ($LASTEXITCODE). Will still check whether CMake is available."
    }

    $candidateBins = @(
        "C:\Program Files\CMake\bin",
        "C:\Program Files (x86)\CMake\bin",
        (Join-Path $env:LOCALAPPDATA "Programs\CMake\bin")
    )

    foreach ($cmakeBin in $candidateBins) {
        if ((Test-Path $cmakeBin) -and (-not ($env:Path -split ';' | Where-Object { $_ -eq $cmakeBin }))) {
            $env:Path += ";$cmakeBin"
        }
    }

    $cmakeCmd = Get-Command "cmake" -ErrorAction SilentlyContinue
    if (-not $cmakeCmd) {
        throw "CMake was installed but is still not available in PATH for current shell. Reopen terminal and retry."
    }

    Write-Success "CMake is available: $($cmakeCmd.Source)"
}

function Import-MsvcBuildEnvironment {
    $vswherePath = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswherePath)) {
        return $false
    }

    $installPath = & $vswherePath -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($installPath)) {
        return $false
    }

    $installPath = $installPath.Trim()
    $devCmd = Join-Path $installPath "Common7\Tools\VsDevCmd.bat"
    $vcVars = Join-Path $installPath "VC\Auxiliary\Build\vcvars64.bat"

    if (Test-Path $devCmd) {
        $initCommand = '"' + $devCmd + '" -no_logo -arch=x64 -host_arch=x64'
    } elseif (Test-Path $vcVars) {
        $initCommand = '"' + $vcVars + '"'
    } else {
        return $false
    }

    $envDump = & cmd.exe /c "$initCommand && set"
    if ($LASTEXITCODE -ne 0 -or -not $envDump) {
        return $false
    }

    foreach ($line in $envDump) {
        $idx = $line.IndexOf('=')
        if ($idx -le 0) {
            continue
        }

        $name = $line.Substring(0, $idx)
        $value = $line.Substring($idx + 1)
        [System.Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }

    return $true
}

function Ensure-MsvcBuildTools {
    param([switch]$AutoInstall)

    if ((Get-Command "cl" -ErrorAction SilentlyContinue) -and (Get-Command "nmake" -ErrorAction SilentlyContinue)) {
        return
    }

    Write-Info "MSVC compiler not detected, trying to initialize Visual Studio build environment..."
    $msvcLoaded = Import-MsvcBuildEnvironment
    if ($msvcLoaded -and (Get-Command "cl" -ErrorAction SilentlyContinue) -and (Get-Command "nmake" -ErrorAction SilentlyContinue)) {
        Write-Success "MSVC build environment initialized."
        return
    }

    $installHint = "MSVC Build Tools not detected. Install with: winget install -e --id Microsoft.VisualStudio.2022.BuildTools --override `"--wait --quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended`""
    if (-not $AutoInstall) {
        throw $installHint
    }

    $wingetCmd = Get-Command "winget" -ErrorAction SilentlyContinue
    if (-not $wingetCmd) {
        throw "$installHint`nAuto install was requested, but winget is not available."
    }

    Write-Info "MSVC Build Tools not found, trying to install via winget..."
    & winget install -e --id Microsoft.VisualStudio.2022.BuildTools --override "--wait --quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended" --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install MSVC Build Tools via winget. $installHint"
    }

    $msvcLoaded = Import-MsvcBuildEnvironment
    if (-not $msvcLoaded -or -not (Get-Command "cl" -ErrorAction SilentlyContinue) -or -not (Get-Command "nmake" -ErrorAction SilentlyContinue)) {
        throw "MSVC Build Tools were installed but are still not available in this shell. Reopen terminal and retry."
    }

    Write-Success "MSVC Build Tools are available."
}

function Update-PyprojectPackageName {
    param(
        [string]$PyprojectPath,
        [string]$NewName
    )

    $content = Get-Content -Path $PyprojectPath -Raw
    $pattern = '(?m)^(?<pre>\s*name\s*=\s*")[^"]*(?<post>"\s*)$'
    $match = [regex]::Match($content, $pattern)
    if (-not $match.Success) {
        throw "Failed to find package name in $PyprojectPath"
    }

    $currentName = $match.Value -replace '(?m)^\s*name\s*=\s*"([^"]*)"\s*$', '$1'
    if ($currentName -eq $NewName) {
        # Even when unchanged, normalize encoding to UTF-8 without BOM.
        $updated = $content
    } else {
        $replacement = "`${pre}$NewName`${post}"
        $updated = [regex]::Replace($content, $pattern, $replacement, 1)
    }

    # Write UTF-8 without BOM; some TOML parsers reject BOM at file start.
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($PyprojectPath, $updated, $utf8NoBom)
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
        $cudaRoot = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
        if (Test-Path $cudaRoot) {
            $detected = Get-ChildItem -Path $cudaRoot -Directory | Sort-Object Name -Descending | Select-Object -First 1
            if ($detected) {
                $env:CUDA_PATH = $detected.FullName
                $cudaBin = Join-Path $env:CUDA_PATH "bin"
                if ((Test-Path $cudaBin) -and (-not ($env:Path -split ';' | Where-Object { $_ -eq $cudaBin }))) {
                    $env:Path += ";$cudaBin"
                }
                Write-Info "Detected CUDA toolkit: $($env:CUDA_PATH)"
            }
        }
    }

    if (-not (Get-Command "nvcc" -ErrorAction SilentlyContinue) -and -not $env:CUDA_PATH) {
        throw "CUDA toolkit not detected. Please install CUDA and ensure nvcc or CUDA_PATH is available."
    }
} elseif ($GpuSupport -eq "ROCM") {
    if (-not (Get-Command "hipcc" -ErrorAction SilentlyContinue) -and -not $env:ROCM_PATH) {
        throw "ROCm toolkit not detected. Please install ROCm and ensure hipcc or ROCM_PATH is available."
    }
}

Ensure-MsvcBuildTools -AutoInstall:$AutoInstallMsvc

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
    $fetchSucceeded = $false
    $maxFetchAttempts = 3
    for ($attempt = 1; $attempt -le $maxFetchAttempts; $attempt++) {
        & git fetch --tags origin
        if ($LASTEXITCODE -eq 0) {
            $fetchSucceeded = $true
            break
        }

        if ($attempt -lt $maxFetchAttempts) {
            Write-Warning-Custom "git fetch failed (attempt $attempt/$maxFetchAttempts). Retrying in 3 seconds..."
            Start-Sleep -Seconds 3
        }
    }

    if (-not $fetchSucceeded) {
        # Fallback to local refs when network is unstable.
        & git rev-parse --verify $RepoRef
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to fetch faiss-wheels refs"
        }
        Write-Warning-Custom "git fetch failed after retries. Continuing with local refs for '$RepoRef'."
    }

    & git checkout $RepoRef
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to checkout faiss-wheels ref: $RepoRef"
    }

    # Force submodules to target commits even if previous builds left local changes.
    & git submodule sync --recursive
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to sync faiss-wheels submodule URLs"
    }

    & git submodule update --init --recursive --force
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