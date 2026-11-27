<#
.SYNOPSIS
    One-click Windows launcher for AegisFlow v2.0 (FastAPI Backend + React 3D Command Center).
.DESCRIPTION
    1. Verifies Python and npm prerequisites.
    2. Starts FastAPI gateway (uvicorn backend.main:app) in a dedicated PowerShell window.
    3. Polls http://127.0.0.1:8000/api/v1/health for up to 15 seconds.
    4. Starts Vite dev server (npm run dev in frontend/) in a dedicated PowerShell window.
    5. Opens http://localhost:5173 in the default browser after 3 seconds.
#>

$ErrorActionPreference = "Stop"

$RepoRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$FrontendDir = Join-Path $RepoRoot "frontend"
$BackendUrl = "http://127.0.0.1:8000"
$HealthUrl = "$BackendUrl/api/v1/health"
$FrontendUrl = "http://localhost:5173"

# Crisp cyan AegisFlow v2.0 startup banner
Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "    ___    ______ ______ ____ _____ ______ __     ____  _       __    " -ForegroundColor Cyan
Write-Host "   /   |  / ____// ____//  _// ___// ____// /    / __ \| |     / /    " -ForegroundColor Cyan
Write-Host "  / /| | / __/  / / __  / /  \__ \/ /_   / /    / / / /| | /| / /     " -ForegroundColor Cyan
Write-Host " / ___ |/ /___ / /_/ /_/ /  ___/ / __/  / /___ / /_/ / | |/ |/ /      " -ForegroundColor Cyan
Write-Host "/_/  |_/_____/ \____//___/ /____/_/    /_____/ \____/  |__/|__/  v2.0 " -ForegroundColor Cyan
Write-Host ""
Write-Host "  Predictive Emergency Corridor Orchestration & 3D Digital Twin       " -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Verify runtime prerequisites
Write-Host "[1/4] Checking prerequisites (python, npm)..." -ForegroundColor Cyan

$PythonCmd = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $PythonCmd) {
    Write-Host "[ERROR] 'python' was not found on PATH. Install Python 3.11+ and retry." -ForegroundColor Red
    exit 1
}

$NpmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($null -eq $NpmCmd) {
    Write-Host "[ERROR] 'npm.cmd' was not found on PATH. Install Node.js 18+ (with npm) and retry." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $FrontendDir "package.json"))) {
    Write-Host "[ERROR] frontend/package.json not found under '$FrontendDir'." -ForegroundColor Red
    exit 1
}

$PythonVersion = (& python --version 2>&1)
$NpmVersion = (& npm.cmd --version 2>&1)
Write-Host ("      Found {0} and npm v{1}" -f $PythonVersion, $NpmVersion) -ForegroundColor DarkCyan

# 2. Spawn FastAPI backend in dedicated PowerShell window
Write-Host "[2/4] Starting FastAPI Gateway ($BackendUrl)..." -ForegroundColor Cyan

$EscapedRoot = $RepoRoot.Replace("'", "''")
$EscapedFrontend = $FrontendDir.Replace("'", "''")

$BackendCommand = @(
    "Set-Location '$EscapedRoot'"
    "`$Host.UI.RawUI.WindowTitle = 'AegisFlow Backend (127.0.0.1:8000)'"
    "Write-Host 'Starting AegisFlow FastAPI Gateway on http://127.0.0.1:8000 ...' -ForegroundColor Cyan"
    "python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"
) -join "; "

$BackendProc = Start-Process -FilePath "powershell.exe" `
    -ArgumentList @("-NoExit", "-Command", $BackendCommand) `
    -WorkingDirectory $RepoRoot `
    -PassThru

# 3. Poll /api/v1/health up to 15 seconds
Write-Host "[3/4] Waiting for backend health check ($HealthUrl)..." -ForegroundColor Cyan
$Healthy = $false
$Response = $null
$Deadline = (Get-Date).AddSeconds(15)

while ((Get-Date) -lt $Deadline) {
    try {
        $Response = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 2
        if (
            $null -ne $Response -and
            ($Response.PSObject.Properties.Name -contains "status") -and
            $Response.status -eq "ok"
        ) {
            $Healthy = $true
            break
        }
    }
    catch {
        $Response = $null
    }
    Start-Sleep -Milliseconds 500
}

if (-not $Healthy) {
    Write-Host "[ERROR] Backend did not report healthy at $HealthUrl within 15 seconds." -ForegroundColor Red
    Write-Host "        Check the 'AegisFlow Backend' PowerShell window for startup errors." -ForegroundColor Yellow
    exit 1
}

$ServiceName = if ($Response.PSObject.Properties.Name -contains "service") { $Response.service } else { "aegisflow-gateway" }
Write-Host "      Backend online and healthy (status=ok, service=$ServiceName)." -ForegroundColor Green

# 4. Spawn Vite React Command Center in dedicated PowerShell window
Write-Host "[4/4] Starting Vite React Command Center ($FrontendUrl)..." -ForegroundColor Cyan

$FrontendCommand = @(
    "Set-Location '$EscapedFrontend'"
    "`$Host.UI.RawUI.WindowTitle = 'AegisFlow Frontend (localhost:5173)'"
    "Write-Host 'Starting AegisFlow 3D Command Center on http://localhost:5173 ...' -ForegroundColor Cyan"
    "npm.cmd run dev"
) -join "; "

$FrontendProc = Start-Process -FilePath "powershell.exe" `
    -ArgumentList @("-NoExit", "-Command", $FrontendCommand) `
    -WorkingDirectory $FrontendDir `
    -PassThru

Write-Host "      Waiting 3 seconds for Vite dev server initialization..." -ForegroundColor DarkCyan
Start-Sleep -Seconds 3

Write-Host "      Opening $FrontendUrl in your default browser..." -ForegroundColor Cyan
Start-Process $FrontendUrl

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Green
Write-Host " AegisFlow v2.0 Live Demo Stack Running" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host ("  Command Center UI : {0}" -f $FrontendUrl) -ForegroundColor White
Write-Host ("  Backend API Docs  : {0}/docs" -f $BackendUrl) -ForegroundColor White
Write-Host ("  Backend Health    : {0}" -f $HealthUrl) -ForegroundColor White
Write-Host ("  WebSocket Stream  : ws://127.0.0.1:8000/ws/corridor") -ForegroundColor White
Write-Host ("  Spawned PIDs      : Backend={0} | Frontend={1}" -f $BackendProc.Id, $FrontendProc.Id) -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Optional Edge CCTV + BEV Vision Node:" -ForegroundColor DarkCyan
Write-Host "    python -m perception.detector --demo-synthetic --show --api-url $BackendUrl" -ForegroundColor Gray
Write-Host ""
Write-Host "  Press Ctrl+C in the spawned terminals to stop the servers." -ForegroundColor Yellow
Write-Host "======================================================================" -ForegroundColor Green
Write-Host ""
