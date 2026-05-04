@echo off
set "ROOT=%~dp0"
start "" /D "%ROOT%" /min powershell -NoProfile -ExecutionPolicy Bypass -STA -WindowStyle Hidden -File "%ROOT%buildar.ps1"
exit /b
