@echo off
setlocal
set "ROOT=%~dp0"
start "" powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -WindowStyle Hidden -File "%ROOT%iniciar.ps1"
endlocal
exit /b
