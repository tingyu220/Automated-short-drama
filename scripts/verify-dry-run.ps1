<#
.SYNOPSIS
    Dry Run 全场景验收：运行 Dry Run 全场景集成测试。
.DESCRIPTION
    1. cd backend && python -m pytest tests/integration/test_dry_run_full_scenario.py -q
    全部通过退出码 0，否则非 0；输出 Dry Run 验收结果摘要。
#>
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot "backend"

Write-Host "==> Dry Run 全场景验收开始"
Write-Host "==> 运行 pytest tests/integration/test_dry_run_full_scenario.py -q"

Push-Location $BackendDir
try {
    python -m pytest tests/integration/test_dry_run_full_scenario.py -q
    $ExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}

if ($ExitCode -eq 0) {
    Write-Host "[PASS] Dry Run 验收：全场景测试全部通过"
} else {
    Write-Host "[FAIL] Dry Run 验收存在失败用例，退出码 $ExitCode"
}

exit $ExitCode
