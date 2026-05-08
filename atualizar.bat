@echo off
setlocal

set "ROOT=%~dp0"
set "SCRIPT=%ROOT%atualizar.ps1"
set "PS_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

if not exist "%SCRIPT%" (
	echo atualizar.ps1 nao encontrado em "%SCRIPT%".
	pause
	exit /b 1
)

if not exist "%PS_EXE%" (
	set "PS_EXE="
	for /f "delims=" %%P in ('where powershell.exe 2^>nul') do (
		if not defined PS_EXE set "PS_EXE=%%P"
	)
)

if not defined PS_EXE (
	echo Windows PowerShell nao foi encontrado neste computador.
	pause
	exit /b 1
)

pushd "%ROOT%" >nul
"%PS_EXE%" -NoProfile -STA -ExecutionPolicy Bypass -File "%SCRIPT%"
set "EXIT_CODE=%ERRORLEVEL%"
popd >nul

if not "%EXIT_CODE%"=="0" (
	echo.
	echo Atualizacao encerrada com erro. Codigo: %EXIT_CODE%
	echo Veja o log em "%ROOT%logs\update.log".
	pause
)

exit /b %EXIT_CODE%
