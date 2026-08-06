<#
.SYNOPSIS
    运行生产验证阶梯（默认 Mock 模式）。
.DESCRIPTION
    调用 python -m backend.interfaces.cli.production_validation；
    -Ladder 指定 single/three/five/ten；-PlanType 指定 test/free/paid_9_9/paid_2_9/both；
    -Real 传入 --real（需环境变量 ALLOW_FINAL_SUBMIT=true）。
    输出 JSON；全部阶梯通过退出码 0，否则退出码 1。
#>
param(
    [ValidateSet("single", "three", "five", "ten")]
    [string]$Ladder = "single",
    [ValidateSet("test", "free", "paid_9_9", "paid_2_9", "both")]
    [string]$PlanType = "test",
    [switch]$Real
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot "backend"

$pythonArgs = @("--ladder", $Ladder, "--plan-type", $PlanType)
if ($Real) {
    $pythonArgs += "--real"
}

Push-Location $BackendDir
try {
    python -m backend.interfaces.cli.production_validation @pythonArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
