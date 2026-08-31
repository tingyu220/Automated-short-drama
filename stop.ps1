# 短剧投放工作台 - 停止脚本
# 双击 stop.bat 即可运行此脚本

$ErrorActionPreference = "SilentlyContinue"

Write-Host ""
Write-Host "=============================" -ForegroundColor Cyan
Write-Host "  停止所有服务..." -ForegroundColor Cyan
Write-Host "=============================" -ForegroundColor Cyan

$stopped = 0

# 停止 Python 进程 (API + Worker)
Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object {
    (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine -match "control_server|automation_worker"
} | ForEach-Object {
    Write-Host "  停止 Python PID=$($_.Id)"
    Stop-Process -Id $_.Id -Force
    $script:stopped++
}

# 停止 Node 进程 (前端 Vite)
Get-Process -Name node -ErrorAction SilentlyContinue | Where-Object {
    (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine -match "vite|npm"
} | ForEach-Object {
    Write-Host "  停止 Node PID=$($_.Id)"
    Stop-Process -Id $_.Id -Force
    $script:stopped++
}

Write-Host ""
if ($stopped -eq 0) {
    Write-Host "  没有运行中的服务进程" -ForegroundColor Yellow
} else {
    Write-Host "  已停止 $stopped 个进程" -ForegroundColor Green
}
Write-Host ""
