<#
.SYNOPSIS
    Dev mode one-click start: backend + frontend (Vite) + Worker.
.DESCRIPTION
    Starts Control Server (127.0.0.1:8765), Vite frontend (127.0.0.1:5173),
    and Automation Worker. Auto-detects Python / npm / Chrome paths.
    Ctrl+C to gracefully stop all child processes.
#>
param(
    [ValidateSet("MOCK", "REAL")]
    [string]$WorkerMode = "MOCK",

    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

# -- Environment detection --
function Resolve-Cmd {
    param([string]$Name)
    $c = Get-Command $Name -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    return $null
}

# Python - prefer system Python 3.12 (has project deps installed)
$pythonExe = $null
$pythonCandidates = @(
    "C:\Users\tingyu\AppData\Local\Programs\Python\Python312\python.exe",
    "C:\Python312\python.exe",
    "D:\pycharm\python\python.exe"
)
foreach ($candidate in $pythonCandidates) {
    if (Test-Path $candidate) {
        $ver = & $candidate -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($ver -ge "3.12") { $pythonExe = $candidate; break }
    }
}
if (-not $pythonExe) { $pythonExe = Resolve-Cmd "python" }
if (-not $pythonExe) {
    Write-Error "Python not found. Install Python 3.12+ or add to PATH."
    exit 1
}
$pythonDir = Split-Path $pythonExe
Write-Host "[env] Python: $pythonExe"

# npm - prefer .cmd version for cmd.exe compatibility
$npmCmd = $null
$npmCandidates = @(
    "C:\Users\tingyu\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\node\npm.cmd",
    "C:\Program Files\nodejs\npm.cmd"
)
foreach ($candidate in $npmCandidates) {
    if (Test-Path $candidate) { $npmCmd = $candidate; break }
}
if (-not $npmCmd) { $npmCmd = Resolve-Cmd "npm" }
if (-not $npmCmd) {
    Write-Error "npm not found. Install Node.js 18+ or add to PATH."
    exit 1
}
$nodeExe = Resolve-Cmd "node"
if (-not $nodeExe) {
    $nodeCandidate = "C:\Users\tingyu\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\node\node.exe"
    if (Test-Path $nodeCandidate) { $nodeExe = $nodeCandidate }
}
if ($nodeExe) { $nodeDir = Split-Path $nodeExe } else { $nodeDir = Split-Path $npmCmd }
Write-Host "[env] npm: $npmCmd"

# Chrome
$chromeExe = Resolve-Cmd "chrome"
if (-not $chromeExe) {
    $chromePaths = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LocalAppData\Google\Chrome\Application\chrome.exe"
    )
    foreach ($p in $chromePaths) {
        if (Test-Path $p) { $chromeExe = $p; break }
    }
}
if ($chromeExe) { Write-Host "[env] Chrome: $chromeExe" }
else { Write-Warning "Chrome not found, skipping browser launch." }

# Inject PATH
$env:PATH = "$pythonDir;$nodeDir;$env:PATH"

# -- Port cleanup --
function Stop-PortProcess {
    param([int]$Port)
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($conns) {
        foreach ($conn in $conns) {
            $p = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
            if ($p) {
                Write-Warning "Port $Port in use by PID $($p.Id) ($($p.ProcessName)), stopping..."
                Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
            }
        }
        Start-Sleep -Seconds 1
    }
}

Stop-PortProcess -Port 8765
Stop-PortProcess -Port 5173

# -- Process tracking --
$script:processes = @()

function Stop-AllProcesses {
    Write-Host ""
    Write-Host "Stopping all services..."
    foreach ($p in $script:processes) {
        if ($p -and -not $p.HasExited) {
            try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
    Write-Host "All services stopped."
}

# -- 0. Database migration --
Write-Host ""
Write-Host "[1/4] Running database migration..."
Set-Location "$ProjectRoot\backend"
& $pythonExe -m backend.infrastructure.database.migrations
if ($LASTEXITCODE -ne 0) {
    Write-Error "Database migration failed."
    exit 1
}
Write-Host "[1/4] Migration done."

# -- Log directory --
$logDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"

# -- 1. Start backend --
Write-Host "[2/4] Starting backend Control Server (127.0.0.1:8765)..."
$backendLog = Join-Path $logDir "backend-$timestamp.log"
$backendErr = Join-Path $logDir "backend-$timestamp.err"
$backendProc = Start-Process -FilePath $pythonExe `
    -ArgumentList "-m", "backend.bootstrap.control_server" `
    -WorkingDirectory "$ProjectRoot\backend" `
    -WindowStyle Hidden `
    -RedirectStandardOutput $backendLog `
    -RedirectStandardError $backendErr `
    -PassThru
$script:processes += $backendProc

# -- 2. Start frontend --
Write-Host "[3/4] Starting Vite frontend (127.0.0.1:5173)..."
$frontendLog = Join-Path $logDir "frontend-$timestamp.log"
$frontendProc = Start-Process -FilePath $npmCmd `
    -ArgumentList "run", "dev" `
    -WorkingDirectory "$ProjectRoot\dashboard" `
    -WindowStyle Hidden `
    -RedirectStandardOutput $frontendLog `
    -RedirectStandardError "$frontendLog.err" `
    -PassThru
$script:processes += $frontendProc

# -- 3. Wait for healthz --
Write-Host "[4/4] Waiting for backend healthz (http://127.0.0.1:8765/healthz)..."
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    if ($backendProc.HasExited) {
        Write-Error "Backend process exited unexpectedly (code=$($backendProc.ExitCode))."
        Stop-AllProcesses
        exit 1
    }
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8765/healthz" -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
    Write-Host -NoNewline "."
}
Write-Host ""

if (-not $ready) {
    Write-Error "Backend startup timed out (30s)."
    Stop-AllProcesses
    exit 1
}
Write-Host "[4/4] Backend is ready."

# -- 4. Set worker mode and start worker --
$runtimeBody = @{ mode = $WorkerMode; confirm_real = ($WorkerMode -eq "REAL") } | ConvertTo-Json
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/runtime/environment" `
        -Method Put -ContentType "application/json" -Body $runtimeBody | Out-Null
    Write-Host "Worker target mode: $WorkerMode"
} catch {
    Write-Warning "Failed to set runtime mode (non-fatal): $($_.Exception.Message)"
}

$workerLog = Join-Path $logDir "worker-$timestamp.log"
$workerProc = Start-Process -FilePath $pythonExe `
    -ArgumentList "-m", "backend.bootstrap.automation_worker", "--mode-check-interval", "1" `
    -WorkingDirectory "$ProjectRoot\backend" `
    -WindowStyle Hidden `
    -RedirectStandardOutput $workerLog `
    -RedirectStandardError "$workerLog.err" `
    -PassThru
$script:processes += $workerProc

# -- 5. Open browser --
if (-not $NoBrowser -and $chromeExe) {
    Start-Process $chromeExe -ArgumentList "--app=http://127.0.0.1:5173"
    Write-Host "Opened Chrome in app mode."
}

# -- Done --
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Workbench started successfully" -ForegroundColor Green
Write-Host "  - Backend API:  http://127.0.0.1:8765" -ForegroundColor Green
Write-Host "  - Frontend:     http://127.0.0.1:5173" -ForegroundColor Green
Write-Host "  - Worker mode:  $WorkerMode" -ForegroundColor Green
Write-Host "  - Press Ctrl+C to stop all services" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# Wait for Ctrl+C
try {
    while ($true) { Start-Sleep -Seconds 1 }
} finally {
    Stop-AllProcesses
}
