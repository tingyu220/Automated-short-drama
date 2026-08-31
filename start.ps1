# 短剧投放工作台 - 一键启动脚本
# 启动 API 服务器、Worker、前端开发服务器
# 双击 start.bat 即可运行此脚本

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = "C:\Users\tingyu\AppData\Local\Programs\Python\Python312\python.exe"
$logDir = Join-Path $root "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

Write-Host ""
Write-Host "=============================" -ForegroundColor Cyan
Write-Host "  短剧投放工作台 - 启动中..." -ForegroundColor Cyan
Write-Host "=============================" -ForegroundColor Cyan
Write-Host ""

# 终止旧进程
Write-Host "[1/4] 清理旧进程..." -NoNewline
Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object {
    (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine -match "control_server|automation_worker"
} | ForEach-Object { Stop-Process -Id $_.Id -Force }
Get-Process -Name node -ErrorAction SilentlyContinue | Where-Object {
    (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine -match "vite|npm"
} | ForEach-Object { Stop-Process -Id $_.Id -Force }
Start-Sleep -Seconds 2
Write-Host " OK" -ForegroundColor Green

# 设置 PYTHONPATH
$env:PYTHONPATH = Join-Path $root "backend\src"

# 启动 API 服务器
Write-Host "[2/4] 启动 API 服务器..." -NoNewline
$apiLog = Join-Path $logDir "api-server.log"
$apiErr = Join-Path $logDir "api-server-err.log"
Start-Process -FilePath $python `
    -ArgumentList "-u", "-m", "backend.bootstrap.control_server" `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $apiLog `
    -RedirectStandardError $apiErr
Start-Sleep -Seconds 5
Write-Host " OK" -ForegroundColor Green

# 启动 Worker
Write-Host "[3/4] 启动 Worker..." -NoNewline
$workerLog = Join-Path $logDir "worker.log"
$workerErr = Join-Path $logDir "worker-err.log"
Start-Process -FilePath $python `
    -ArgumentList "-u", "-m", "backend.bootstrap.automation_worker" `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $workerLog `
    -RedirectStandardError $workerErr
Start-Sleep -Seconds 5
Write-Host " OK" -ForegroundColor Green

# 启动前端
Write-Host "[4/4] 启动前端..." -NoNewline
$frontLog = Join-Path $logDir "frontend.log"
$frontErr = Join-Path $logDir "frontend-err.log"
Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "npm run dev" `
    -WorkingDirectory (Join-Path $root "dashboard") `
    -WindowStyle Hidden `
    -RedirectStandardOutput $frontLog `
    -RedirectStandardError $frontErr
Start-Sleep -Seconds 5
Write-Host " OK" -ForegroundColor Green

# 健康检查
Write-Host ""
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8765/healthz" -Method Get -TimeoutSec 5
    Write-Host "=============================" -ForegroundColor Green
    Write-Host "  启动成功!" -ForegroundColor Green
    Write-Host "=============================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  工作台:   http://127.0.0.1:5173" -ForegroundColor Yellow
    Write-Host "  API:      http://127.0.0.1:8765" -ForegroundColor Gray
    Write-Host "  日志目录:  $logDir" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  停止服务: 双击 stop.bat" -ForegroundColor Gray
    Write-Host ""
} catch {
    Write-Host "=============================" -ForegroundColor Red
    Write-Host "  启动失败! 请检查日志:" -ForegroundColor Red
    Write-Host "=============================" -ForegroundColor Red
    Write-Host "  API 错误日志: $apiErr"
    Write-Host ""
    Get-Content $apiErr -Tail 20 -ErrorAction SilentlyContinue
}
