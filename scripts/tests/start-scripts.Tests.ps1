$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

Describe "启动脚本" {
    It "开发启动脚本默认模拟模式并支持真实模式" {
        $content = Get-Content -Raw (Join-Path $ProjectRoot "scripts\start.ps1")

        $content | Should Match '\[ValidateSet\("MOCK", "REAL"\)\]'
        $content | Should Match '\$WorkerMode = "MOCK"'
        $content | Should Match '/api/runtime/environment'
    }

    It "正式启动脚本支持选择 Worker 模式" {
        $content = Get-Content -Raw (Join-Path $ProjectRoot "scripts\start-workbench.ps1")

        $content | Should Match '\[ValidateSet\("MOCK", "REAL"\)\]'
        $content | Should Match '/api/runtime/environment'
    }

    It "批处理入口使用 PowerShell 7" {
        $content = Get-Content -Raw (Join-Path $ProjectRoot "scripts\start.bat")

        $content | Should Match 'pwsh\.exe'
        $content | Should Not Match '^powershell\s'
    }
}
