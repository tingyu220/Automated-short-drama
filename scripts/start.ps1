<#
.SYNOPSIS
    开发模式一键启动：后端 + 前端（Vite）+ Worker。
.DESCRIPTION
    启动 Control Server（127.0.0.1:8765）、Vite 前端（127.0.0.1:5173）、
    Automation Worker，等待 healthz 就绪后 Chrome 应用模式打开前端。
    Ctrl+C 优雅停止所有子进程。
#>
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

$jobs = @()

# 0. 执行数据库迁移
Write-Host "执行数据库迁移 ..."
Set-Location "$ProjectRoot\backend"
python -m backend.infrastructure.database.migrations
if ($LASTEXITCODE -ne 0) {
    Write-Error "数据库迁移失败，退出。"
    exit 1
}
Write-Host "数据库迁移完成。"


# 1. 启动后端
$backendJob = Start-Job -Name "Backend" -ArgumentList $ProjectRoot {
    param($root)
    Set-Location "$root\backend"
    python -m backend.bootstrap.control_server
}
$jobs += $backendJob

# 2. 启动前端 (Vite)
$frontendJob = Start-Job -Name "Frontend" -ArgumentList $ProjectRoot {
    param($root)
    Set-Location "$root\dashboard"
    npm run dev
}
$jobs += $frontendJob

# 3. 启动 Worker
$workerJob = Start-Job -Name "Worker" -ArgumentList $ProjectRoot {
    param($root)
    Set-Location "$root\backend"
    python -m backend.bootstrap.automation_worker
}
$jobs += $workerJob

# 等待 healthz 就绪
Write-Host "等待后端就绪 (http://127.0.0.1:8765/healthz) ..."
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8765/healthz" -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
    }
    Start-Sleep -Seconds 1
}

if ($ready) {
    Write-Host "后端已就绪，打开 Chrome ..."
    Start-Process "chrome.exe" -ArgumentList "--app=http://127.0.0.1:5173"
    Write-Host "开发环境启动完成。按 Ctrl+C 停止所有服务。"
} else {
    Write-Error "后端启动超时，请检查日志。"
}

# 等待 Ctrl+C 并清理
try {
    while ($true) {
        Start-Sleep -Seconds 1
    }
} finally {
    Write-Host "正在停止所有服务..."
    foreach ($job in $jobs) {
        Stop-Job $job
        Remove-Job $job -Force
    }
    Write-Host "所有服务已停止。"
}
*** End of File
