<#
.SYNOPSIS
    Phase 8 集成验收：运行 Phase 8 全场景集成测试。
.DESCRIPTION
    1. cd backend && python -m pytest tests/integration/test_phase8_full_scenario.py -q
    全部通过退出码 0，否则非 0；输出 Phase 8 验收结果摘要。
#>
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot "backend"

Write-Host "==> Phase 8 集成验收开始"
Write-Host "==> 运行 pytest tests/integration/test_phase8_full_scenario.py -q"

$ExitCode = 1
Push-Location $BackendDir
try {
    python -m pytest tests/integration/test_phase8_full_scenario.py -q
    $ExitCode = $LASTEXITCODE
} catch {
    Write-Host "[FAIL] Phase 8 验收脚本执行异常: $($_.Exception.Message)"
    $ExitCode = 1
} finally {
    Pop-Location
}

if ($ExitCode -eq 0) {
    Write-Host "[PASS] Phase 8 验收：全场景测试全部通过"
} else {
    Write-Host "[FAIL] Phase 8 验收存在失败用例，退出码 $ExitCode"
}

exit $ExitCode
