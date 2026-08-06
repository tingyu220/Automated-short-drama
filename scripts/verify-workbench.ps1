<#
.SYNOPSIS
    前后端联调验收：构建前端、临时库启动后端并检查 API 与静态托管。
.DESCRIPTION
    固定流程与检查点：
    1. cd dashboard && npm run build
    2. 设置临时 WORKBUDDY_DATABASE_URL 并启动 Control Server
    3. 等待 http://127.0.0.1:8765/healthz 返回 200
    4. 检查 /api/tasks、/api/queue、/api/rules、/api/accounts/overview、
       /api/exceptions、/api/records/ledgers 均返回 200
    5. 检查 GET / 返回 200（FastAPI 托管前端 dist）
    全部通过退出码 0，否则非 0；脚本结束可靠停止后端进程。
#>
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot "backend"
$DashboardDir = Join-Path $ProjectRoot "dashboard"
$BaseUrl = "http://127.0.0.1:8765"
$ApiEndpoints = @(
    "/api/tasks"
    "/api/queue"
    "/api/rules"
    "/api/accounts/overview"
    "/api/exceptions"
    "/api/records/ledgers"
)

$script:ExitCode = 0
$BackendProcess = $null
$OriginalDatabaseUrl = $env:WORKBUDDY_DATABASE_URL
$TempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("workbuddy-verify-" + [System.Guid]::NewGuid().ToString("N"))

function Write-Step([string]$Message) {
    Write-Host "==> $Message"
}

function Get-HttpStatus([string]$Uri) {
    try {
        $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 10
        return [int]$response.StatusCode
    } catch {
        return $null
    }
}

function Assert-Endpoint([string]$Name, [string]$Uri) {
    $status = Get-HttpStatus $Uri
    if ($status -eq 200) {
        Write-Host "[PASS] $Name -> 200"
        return
    }
    Write-Host "[FAIL] $Name -> $status"
    $script:ExitCode = 1
}

function Stop-Backend {
    if ($null -ne $BackendProcess -and -not $BackendProcess.HasExited) {
        Stop-Process -Id $BackendProcess.Id -Force -ErrorAction SilentlyContinue
        Wait-Process -Id $BackendProcess.Id -Timeout 10 -ErrorAction SilentlyContinue
        Write-Host "后端进程已停止 (PID=$($BackendProcess.Id))"
    }
}

try {
    $listener = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        Write-Host "[FAIL] 端口 8765 已被占用，请先停止既有服务后重试。"
        throw "端口 8765 已被占用"
    }

    Write-Step "步骤 1/5：构建前端 dashboard"
    Push-Location $DashboardDir
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) {
            throw "前端构建失败，npm 退出码 $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
    Write-Host "[PASS] dashboard 构建完成"

    Write-Step "步骤 2/5：使用临时数据库启动后端"
    $null = New-Item -ItemType Directory -Path $TempDir -Force
    $DbPath = Join-Path $TempDir "verify.db"
    $DbUrl = "sqlite:///" + ($DbPath -replace "\\", "/")
    $stdoutLog = Join-Path $TempDir "backend.stdout.log"
    $stderrLog = Join-Path $TempDir "backend.stderr.log"

    $env:WORKBUDDY_DATABASE_URL = $DbUrl
    try {
        $BackendProcess = Start-Process -FilePath "python" `
            -ArgumentList @("-m", "backend.bootstrap.control_server") `
            -WorkingDirectory $BackendDir `
            -WindowStyle Hidden `
            -RedirectStandardOutput $stdoutLog `
            -RedirectStandardError $stderrLog `
            -PassThru
    } finally {
        if ($null -eq $OriginalDatabaseUrl) {
            Remove-Item Env:WORKBUDDY_DATABASE_URL -ErrorAction SilentlyContinue
        } else {
            $env:WORKBUDDY_DATABASE_URL = $OriginalDatabaseUrl
        }
    }
    Write-Host "后端已启动 (PID=$($BackendProcess.Id), DB=$DbUrl)"

    Write-Step "步骤 3/5：等待 /healthz 返回 200"
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        if ((Get-HttpStatus "$BaseUrl/healthz") -eq 200) {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) {
        Write-Host "[FAIL] /healthz 等待超时"
        if (Test-Path $stderrLog) {
            Write-Host "--- backend.stderr.log ---"
            Get-Content $stderrLog
        }
        throw "/healthz 未就绪"
    }
    Write-Host "[PASS] /healthz -> 200"

    Write-Step "步骤 4/5：检查核心 API 契约"
    foreach ($endpoint in $ApiEndpoints) {
        Assert-Endpoint $endpoint ($BaseUrl + $endpoint)
    }

    Write-Step "步骤 5/5：检查 FastAPI 托管前端 GET /"
    Assert-Endpoint "GET /" $BaseUrl

    if ($script:ExitCode -eq 0) {
        Write-Host "前后端联调验收通过。"
    } else {
        Write-Host "前后端联调验收存在失败项。"
    }
} catch {
    Write-Host "[ERROR] $($_.Exception.Message)"
    $script:ExitCode = 1
} finally {
    Stop-Backend

    $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    $resolvedTemp = [System.IO.Path]::GetFullPath($TempDir)
    $isOwnTempDir = $resolvedTemp.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
        (Split-Path -Leaf $resolvedTemp).StartsWith("workbuddy-verify-")
    if ($isOwnTempDir -and (Test-Path $resolvedTemp)) {
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force -ErrorAction SilentlyContinue
    }

    if ($null -eq $OriginalDatabaseUrl) {
        Remove-Item Env:WORKBUDDY_DATABASE_URL -ErrorAction SilentlyContinue
    } else {
        $env:WORKBUDDY_DATABASE_URL = $OriginalDatabaseUrl
    }
}

exit $script:ExitCode
