@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
echo.
echo 正在启动短剧投放工作台...
echo.
pwsh.exe -ExecutionPolicy Bypass -NoProfile -File "%~dp0start.ps1"
echo.
pause
