@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
set "SCRIPT=%ROOT%launchers\instalar.ps1"
set "LAUNCHER=%ROOT%launchers\instalar.vbs"
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

if /i "%~1"=="--check" (
	if not exist "%SCRIPT%" (
		echo [ERRO] instalar.ps1 nao encontrado em "%SCRIPT%".
		exit /b 1
	)
	echo ROOT=%ROOT%
	echo SCRIPT=%SCRIPT%
	for %%F in ("%SCRIPT%") do echo SCRIPT_LAST_WRITE=%%~tF
	findstr /b /c:"$INSTALLER_REVISION =" "%SCRIPT%" 2>nul
	echo POWERSHELL=%PS%
	echo OK: launcher pronto.
	exit /b 0
)

if /i "%~1"=="--debug" goto debug
if /i "%~1"=="/debug" goto debug
if /i "%~1"=="debug" goto debug

start "" /b "%SystemRoot%\System32\wscript.exe" //nologo "%LAUNCHER%" %*
exit /b 0

:debug
"%PS%" -NoProfile -STA -ExecutionPolicy Bypass -File "%SCRIPT%"
exit /b %ERRORLEVEL%
