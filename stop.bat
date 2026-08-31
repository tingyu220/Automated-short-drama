@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
echo.
echo 正在停止所有服务...
echo.
pwsh.exe -ExecutionPolicy Bypass -NoProfile -File "%~dp0stop.ps1"
echo.
pause
