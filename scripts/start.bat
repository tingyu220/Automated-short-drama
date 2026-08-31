@echo off
REM Dev mode one-click start (all windows hidden)
start /b pwsh.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0start.ps1" %*
