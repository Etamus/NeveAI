@echo off
SETLOCAL ENABLEDELAYEDEXPANSION
chcp 65001 >nul
title Neve AI

echo.
echo  ==========================================
echo    Neve AI - Iniciando...
echo  ==========================================
echo.

SET "ROOT=%~dp0"
SET "VENV_PY=%ROOT%backend\neveai\venv\Scripts\python.exe"
SET "VENV_PYW=%ROOT%backend\neveai\venv\Scripts\pythonw.exe"
SET "BACKEND=%ROOT%backend"

:: Verifica se o venv existe
if not exist "%VENV_PY%" (
    echo  [ERRO] Ambiente Python nao encontrado.
    echo         Execute instalar.bat primeiro.
    pause
    exit /b 1
)

:: Encerra processos anteriores na porta 8080
echo  Encerrando processos anteriores...
powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort 8080 -EA SilentlyContinue).OwningProcess | Where-Object { $_ -and $_ -ne 0 } | Sort-Object -Unique | ForEach-Object { Stop-Process -Id $_ -Force -EA SilentlyContinue }"

:: Inicia o backend (serve o frontend de producao na mesma porta)
echo  Iniciando backend (porta 8080)...
start "Neve AI - Backend" powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:PYTHONIOENCODING='utf-8'; $env:PYTHONPATH='%BACKEND%'; Set-Location '%BACKEND%'; & '%VENV_PY%' -m uvicorn neveai.main:app --host 0.0.0.0 --port 8080"

:: Aguarda o backend responder em UMA unica instancia do PowerShell (polling 250ms)
echo  Aguardando backend carregar...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='SilentlyContinue'; $start=[DateTime]::UtcNow; $warned=$false; while ($true) { try { $r=[System.Net.HttpWebRequest]::Create('http://127.0.0.1:8080/health'); $r.Timeout=500; $r.Method='GET'; $resp=$r.GetResponse(); $resp.Close(); break } catch { $el=([DateTime]::UtcNow - $start).TotalSeconds; if ($el -gt 120) { Write-Host '  AVISO: backend nao respondeu em 120s.'; break } if ($el -gt 10 -and -not $warned) { Write-Host '  Pode levar 20-60 segundos na primeira vez...'; $warned=$true } Start-Sleep -Milliseconds 250 } }"

echo  Backend pronto!
echo.
echo  ==========================================
echo    Neve AI esta rodando!
echo    Acesse: http://localhost:8080
echo  ==========================================
echo.
start "" "%VENV_PYW%" "%ROOT%neve_window.py"
ENDLOCAL
exit