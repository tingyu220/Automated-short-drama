<#
.SYNOPSIS
    Phase 10 acceptance: Worker real orchestration executor mock full-link.
.DESCRIPTION
    1. cd backend && python -m pytest tests/integration/test_phase10_full_scenario.py -q
    Exit 0 when all tests pass, otherwise non-zero.
#>
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot "backend"
$PassMarker = [System.Text.Encoding]::UTF8.GetString(
    [byte[]](0x5B,0x50,0x41,0x53,0x53,0x5D,0x20,0x50,0x68,0x61,0x73,0x65,0x20,0x31,0x30,0x20,0xE9,0xAA,0x8C,0xE6,0x94,0xB6,0xEF,0xBC,0x9A,0x4D,0x6F,0x63,0x6B,0x20,0xE5,0x85,0xA8,0xE9,0x93,0xBE,0xE8,0xB7,0xAF,0xE9,0x80,0x9A,0xE8,0xBF,0x87)
)

Write-Host "==> Phase 10 acceptance start"
Write-Host "==> Run pytest tests/integration/test_phase10_full_scenario.py -q"

$ExitCode = 1
Push-Location $BackendDir
try {
    python -m pytest tests/integration/test_phase10_full_scenario.py -q
    $ExitCode = $LASTEXITCODE
} catch {
    Write-Host "[FAIL] Phase 10 verify script exception: $($_.Exception.Message)"
    $ExitCode = 1
} finally {
    Pop-Location
}

if ($ExitCode -eq 0) {
    Write-Host $PassMarker
} else {
    Write-Host "[FAIL] Phase 10 acceptance failed with exit code $ExitCode"
}

exit $ExitCode
