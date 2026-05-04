@echo off
set "ROOT=%~dp0"
start "" /D "%ROOT%" /min powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%ROOT%atualizar.ps1"
exit /b
