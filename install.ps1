<#
    CardioGuard AI — Automated Setup (Windows / PowerShell)
    =======================================================
    Creates the Python virtual environment, installs backend dependencies,
    generates config files from their templates, and installs the dashboard's
    npm packages.

    Usage:
        .\install.ps1                  # full setup
        .\install.ps1 -SkipDashboard   # backend only
        .\install.ps1 -SkipBackend     # dashboard only

    The script never overwrites an existing config file.
#>

param(
    [switch]$SkipBackend,
    [switch]$SkipDashboard
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$warnings = New-Object System.Collections.ArrayList
$todo     = New-Object System.Collections.ArrayList

function Write-Step   ($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Write-Ok     ($m) { Write-Host "    [ok]   $m" -ForegroundColor Green }
function Write-Info   ($m) { Write-Host "    $m" -ForegroundColor Gray }
function Write-Warn   ($m) { Write-Host "    [warn] $m" -ForegroundColor Yellow; [void]$warnings.Add($m) }
function Add-Todo     ($m) { [void]$todo.Add($m) }

function Test-Command ($name) {
    $c = Get-Command $name -ErrorAction SilentlyContinue
    return ($null -ne $c)
}

Write-Host ""
Write-Host "  CardioGuard AI - Setup" -ForegroundColor White
Write-Host "  ======================" -ForegroundColor White
Write-Host "  $root" -ForegroundColor DarkGray

# ─── 1. Prerequisites ────────────────────────────────────────────────────────
Write-Step "Checking prerequisites"

if (-not (Test-Command "python")) {
    Write-Host "    [fail] Python was not found on PATH." -ForegroundColor Red
    Write-Host "           Install Python 3.12 from https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host "           and tick 'Add python.exe to PATH' during setup." -ForegroundColor Red
    exit 1
}

$pyVersion = (python --version) -replace "Python ", ""
Write-Ok "Python $pyVersion"
$parts = $pyVersion.Split(".")
$major = [int]$parts[0]
$minor = [int]$parts[1]
if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
    Write-Host "    [fail] Python 3.10 or newer is required (3.12 recommended)." -ForegroundColor Red
    exit 1
}
if ($minor -ne 12) {
    Write-Warn "Project targets Python 3.12; you have $pyVersion. Pinned wheels may not resolve."
}

if (Test-Command "node") {
    Write-Ok "Node $(node --version)"
} else {
    Write-Warn "Node.js not found - the dashboard cannot be installed or run."
    $SkipDashboard = $true
    Add-Todo "Install Node.js 18 LTS or newer from https://nodejs.org, then re-run: .\install.ps1 -SkipBackend"
}

if (Test-Command "git") { Write-Ok "Git $((git --version) -replace 'git version ','')" }

# ─── 2. Python environment ───────────────────────────────────────────────────
if (-not $SkipBackend) {
    Write-Step "Setting up the Python environment"

    if (Test-Path ".venv") {
        Write-Info ".venv already exists - reusing it"
    } else {
        Write-Info "Creating .venv ..."
        python -m venv .venv
        Write-Ok "Virtual environment created"
    }

    $venvPython = Join-Path $root ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Host "    [fail] .venv\Scripts\python.exe is missing - the venv is broken." -ForegroundColor Red
        Write-Host "           Delete the .venv folder and re-run this script." -ForegroundColor Red
        exit 1
    }

    Write-Info "Upgrading pip ..."
    & $venvPython -m pip install --upgrade pip --quiet
    Write-Info "Installing backend dependencies (this can take a few minutes) ..."
    & $venvPython -m pip install -r requirements.txt --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "Backend dependencies installed"
    } else {
        Write-Warn "pip reported errors - review the output above."
    }
}

# ─── 3. Config files from templates ──────────────────────────────────────────
Write-Step "Preparing configuration files"

# 3a. Firmware config (device 1)
$fwExample = "firmware\cardioguard\config.h.example"
$fwConfig  = "firmware\cardioguard\config.h"
if (Test-Path $fwConfig) {
    Write-Info "$fwConfig already exists - left untouched"
} elseif (Test-Path $fwExample) {
    Copy-Item $fwExample $fwConfig
    Write-Ok "Created $fwConfig from the template"
    Add-Todo "Edit $fwConfig - Wi-Fi SSID/password (2.4 GHz only), CLOUD_API_URL, PATIENT_ID, DEVICE_ID, GOOGLE_GEO_KEY"
} else {
    Write-Warn "$fwExample not found - cannot generate the firmware config"
}

# 3b. Dashboard environment
$envExample = "dashboard\.env.local.example"
$envLocal   = "dashboard\.env.local"
if (Test-Path $envLocal) {
    Write-Info "$envLocal already exists - left untouched"
} elseif (Test-Path $envExample) {
    Copy-Item $envExample $envLocal
    Write-Ok "Created $envLocal from the template"
    Add-Todo "Edit $envLocal - paste the Firebase web config (all VITE_* values)"
} else {
    Write-Warn "$envExample not found - cannot generate the dashboard env file"
}

# 3c. Firebase service account key
if (Test-Path "firebase_credentials.json") {
    Write-Ok "firebase_credentials.json present"
} else {
    Write-Warn "firebase_credentials.json is missing - Firebase logging will be disabled"
    Add-Todo "Download the service-account key: Firebase Console > Project settings > Service accounts > Generate new private key, then save it to the project root as firebase_credentials.json"
}

# 3d. Model presence
if (Test-Path "ai\cardioguard_model.onnx") {
    Write-Ok "ai\cardioguard_model.onnx present"
} else {
    Write-Warn "ai\cardioguard_model.onnx is missing - the API will not start"
    Add-Todo "Produce the model: python export_onnx.py  (requires ai\best_model.keras)"
}

# ─── 4. Dashboard dependencies ───────────────────────────────────────────────
if (-not $SkipDashboard) {
    Write-Step "Installing dashboard dependencies"
    Push-Location "dashboard"
    try {
        Write-Info "Running npm install ..."
        npm install --no-fund --no-audit
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "Dashboard dependencies installed"
        } else {
            Write-Warn "npm install reported errors - review the output above."
        }
    } finally {
        Pop-Location
    }
}

# ─── 5. Summary ──────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  --------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "  Setup complete" -ForegroundColor White
Write-Host "  --------------------------------------------------------" -ForegroundColor DarkGray

if ($warnings.Count -gt 0) {
    Write-Host ""
    Write-Host "  Warnings:" -ForegroundColor Yellow
    foreach ($w in $warnings) { Write-Host "    - $w" -ForegroundColor Yellow }
}

if ($todo.Count -gt 0) {
    Write-Host ""
    Write-Host "  Before the system will run, you still need to:" -ForegroundColor White
    $i = 1
    foreach ($t in $todo) { Write-Host "    $i. $t" -ForegroundColor White; $i++ }
}

Write-Host ""
Write-Host "  Then start the system:" -ForegroundColor White
Write-Host "    Backend    .venv\Scripts\Activate.ps1" -ForegroundColor Gray
Write-Host "               uvicorn cloud_api:app --host 0.0.0.0 --port 8000" -ForegroundColor Gray
Write-Host "    Dashboard  cd dashboard; npm run dev" -ForegroundColor Gray
Write-Host "    Firmware   open firmware\cardioguard\cardioguard.ino in Arduino IDE 2.x" -ForegroundColor Gray
Write-Host ""
Write-Host "  Full instructions: docs\USER_MANUAL.md" -ForegroundColor DarkGray
Write-Host ""
