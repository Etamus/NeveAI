@echo off
set "ROOT=%~dp0"
start "" /D "%ROOT%" /min powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%ROOT%instalar.ps1"
exit /b
