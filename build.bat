@echo off
chcp 65001 >nul
title Neve AI — Build e Deploy

cd /d "%~dp0"

echo.
echo  ╔══════════════════════════════════╗
echo  ║     Neve AI — Build e Deploy     ║
echo  ╚══════════════════════════════════╝
echo.
echo  [1/2] Executando npm run build...
echo.

call npm run build
if %ERRORLEVEL% neq 0 (
    echo.
    echo  [ERRO] Build falhou. Verifique os erros acima.
    pause
    exit /b 1
)

echo.
echo  [2/2] Copiando build para o backend...
echo.

robocopy "build" "backend\neveai\frontend" /E /IS /IT /NFL /NDL /NJH /NJS >nul
if %ERRORLEVEL% geq 8 (
    echo  [ERRO] Deploy falhou.
    pause
    exit /b 1
)

echo.
echo  ══════════════════════════════════════
echo   Build e deploy concluidos com sucesso!
echo  ══════════════════════════════════════
echo.
pause
