<#
.SYNOPSIS
    Phase 9 生产验证验收：Mock 模式报告落盘与总体 PASS 校验。
.DESCRIPTION
    依次运行 Mock 模式 single/three/five/ten（plan-type test）；
    每步校验退出码 0、stdout JSON report_path 存在且报告含总体 PASS。
    全部通过退出 0，否则退出 1。
#>
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot "backend"
$Ladders = @("single", "three", "five", "ten")
$PassMarker = [System.Text.Encoding]::UTF8.GetString(
    [byte[]](0x2A, 0x2A, 0xE6, 0x80, 0xBB, 0xE4, 0xBD, 0x93, 0x2A, 0x2A, 0x3A, 0x20, 0x50, 0x41, 0x53, 0x53)
)
$AllPassed = $true

Write-Host "==> Phase 9 验收开始"

Push-Location $BackendDir
try {
    foreach ($Ladder in $Ladders) {
        Write-Host "==> 运行 Mock $Ladder"
        $Output = python -m backend.interfaces.cli.production_validation --ladder $Ladder --plan-type test
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[FAIL] $Ladder 退出码 $LASTEXITCODE"
            $AllPassed = $false
            continue
        }
        $Payload = ($Output -join "`n") | ConvertFrom-Json
        if (-not $Payload.report_path -or -not (Test-Path -LiteralPath $Payload.report_path)) {
            Write-Host "[FAIL] $Ladder 报告路径缺失或不存在"
            $AllPassed = $false
            continue
        }
        $ReportBytes = [System.IO.File]::ReadAllBytes($Payload.report_path)
        $ReportText = [System.Text.Encoding]::UTF8.GetString($ReportBytes)
        if ($ReportText.IndexOf($PassMarker) -lt 0) {
            Write-Host "[FAIL] $Ladder 报告总体非 PASS"
            $AllPassed = $false
            continue
        }
        Write-Host "[PASS] $Ladder"
    }
} catch {
    Write-Host "[FAIL] Phase 9 验收脚本执行异常: $($_.Exception.Message)"
    $AllPassed = $false
} finally {
    Pop-Location
}

if ($AllPassed) {
    Write-Host "[PASS] Phase 9 验收：全部阶梯通过"
    exit 0
} else {
    Write-Host "[FAIL] Phase 9 验收存在失败阶梯"
    exit 1
}
