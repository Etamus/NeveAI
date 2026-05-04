@echo off
set "ROOT=%~dp0"
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
start "" /D "%ROOT%" /min "%PS%" -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File "%ROOT%atualizar.ps1"
exit /b
