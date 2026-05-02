@echo off
start "" /min powershell -NoProfile -ExecutionPolicy Bypass -STA -WindowStyle Hidden -File "%~dp0buildar.ps1"
exit
