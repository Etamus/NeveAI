@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul

set "ROOT=%~dp0"
set "SCRIPT=%ROOT%instalar.ps1"
set "LOGDIR=%ROOT%logs"
set "LAUNCHLOG=%LOGDIR%\install-launcher.log"
set "STATEFILE=%LOGDIR%\install-state.txt"

if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>nul

if not exist "%SCRIPT%" (
	echo [ERRO] instalar.ps1 nao encontrado em "%SCRIPT%".
	echo [ERRO] instalar.ps1 nao encontrado em "%SCRIPT%".>>"%LAUNCHLOG%"
	pause
	exit /b 1
)

set "PS="
if exist "%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe" set "PS=%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
if not defined PS if exist "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not defined PS if exist "%SystemRoot%\SysWOW64\WindowsPowerShell\v1.0\powershell.exe" set "PS=%SystemRoot%\SysWOW64\WindowsPowerShell\v1.0\powershell.exe"
if not defined PS for /f "delims=" %%P in ('where powershell.exe 2^>nul') do if not defined PS set "PS=%%P"

set "PSW="
if exist "%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershellw.exe" set "PSW=%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershellw.exe"
if not defined PSW if exist "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershellw.exe" set "PSW=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershellw.exe"
if not defined PSW if exist "%SystemRoot%\SysWOW64\WindowsPowerShell\v1.0\powershellw.exe" set "PSW=%SystemRoot%\SysWOW64\WindowsPowerShell\v1.0\powershellw.exe"
if not defined PSW for /f "delims=" %%P in ('where powershellw.exe 2^>nul') do if not defined PSW set "PSW=%%P"

if not defined PS (
	echo [ERRO] Windows PowerShell nao encontrado neste computador.
	echo [ERRO] Windows PowerShell nao encontrado neste computador.>>"%LAUNCHLOG%"
	pause
	exit /b 1
)

if /i "%~1"=="--check" (
	echo ROOT=%ROOT%
	echo SCRIPT=%SCRIPT%
	for %%F in ("%SCRIPT%") do echo SCRIPT_LAST_WRITE=%%~tF
	findstr /b /c:"$INSTALLER_REVISION =" "%SCRIPT%" 2>nul
	echo POWERSHELL=%PS%
	echo LOG=%LAUNCHLOG%
	echo STATE=%STATEFILE%
	echo OK: launcher pronto.
	exit /b 0
)

set "PS_WINDOW=-WindowStyle Hidden"
set "PS_WINDOWLESS=1"
if /i "%~1"=="--debug" (
	set "PS_WINDOW="
	set "PS_WINDOWLESS="
)
if /i "%~1"=="/debug" (
	set "PS_WINDOW="
	set "PS_WINDOWLESS="
)
if /i "%~1"=="debug" (
	set "PS_WINDOW="
	set "PS_WINDOWLESS="
)

set "START_PAGE=home"
if /i "%~1"=="--page" set "START_PAGE=%~2"
if /i "%~1"=="/page" set "START_PAGE=%~2"
if /i "%~1"=="page" set "START_PAGE=%~2"
if /i "%START_PAGE%"=="instalar" set "START_PAGE=install"
if /i "%START_PAGE%"=="atualizar" set "START_PAGE=update"
if /i "%START_PAGE%"=="buildar" set "START_PAGE=build"
if /i not "%START_PAGE%"=="home" if /i not "%START_PAGE%"=="install" if /i not "%START_PAGE%"=="update" if /i not "%START_PAGE%"=="build" set "START_PAGE=home"

set "NEVE_INSTALLER_ROOT=%ROOT%"
set "NEVE_INSTALLER_SCRIPT=%SCRIPT%"
set "NEVE_INSTALLER_START_PAGE=%START_PAGE%"

echo [%date% %time%] Iniciando hub com "%PS%".>>"%LAUNCHLOG%"
for %%F in ("%SCRIPT%") do echo [%date% %time%] SCRIPT_LAST_WRITE=%%~tF>>"%LAUNCHLOG%"
findstr /b /c:"$INSTALLER_REVISION =" "%SCRIPT%" >>"%LAUNCHLOG%" 2>nul

if defined PSW if defined PS_WINDOWLESS (
	echo [%date% %time%] Iniciando hub sem console com "%PSW%".>>"%LAUNCHLOG%"
	start "" "%PSW%" -NoProfile -STA -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; try { Set-Location -LiteralPath $env:NEVE_INSTALLER_ROOT; & $env:NEVE_INSTALLER_SCRIPT -StartPage $env:NEVE_INSTALLER_START_PAGE; exit 0 } catch { $msg = if ($_.Exception) { $_.Exception.Message } else { [string]$_ }; $log = Join-Path $env:NEVE_INSTALLER_ROOT 'logs\install-launcher.log'; Add-Content -LiteralPath $log -Value ('[FATAL] ' + $msg) -Encoding UTF8; try { Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show(('Falha ao abrir o hub.' + [Environment]::NewLine + [Environment]::NewLine + 'Veja logs\install-launcher.log' + [Environment]::NewLine + [Environment]::NewLine + $msg), 'Neve AI - Hub', 'OK', 'Error') | Out-Null } catch { }; exit 1 }"
	exit /b 0
)

"%PS%" -NoProfile -STA -ExecutionPolicy Bypass %PS_WINDOW% -Command "$ErrorActionPreference='Stop'; try { Set-Location -LiteralPath $env:NEVE_INSTALLER_ROOT; & $env:NEVE_INSTALLER_SCRIPT -StartPage $env:NEVE_INSTALLER_START_PAGE; exit 0 } catch { $msg = if ($_.Exception) { $_.Exception.Message } else { [string]$_ }; $log = Join-Path $env:NEVE_INSTALLER_ROOT 'logs\install-launcher.log'; Add-Content -LiteralPath $log -Value ('[FATAL] ' + $msg) -Encoding UTF8; try { Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show(('Falha ao abrir o hub.' + [Environment]::NewLine + [Environment]::NewLine + 'Veja logs\install-launcher.log' + [Environment]::NewLine + [Environment]::NewLine + $msg), 'Neve AI - Hub', 'OK', 'Error') | Out-Null } catch { Write-Host $msg }; exit 1 }"
set "RC=%ERRORLEVEL%"

set "STATE=missing"
if exist "%STATEFILE%" set /p STATE=<"%STATEFILE%"
echo [%date% %time%] PowerShell saiu com codigo %RC%; estado=%STATE%.>>"%LAUNCHLOG%"

if not "%RC%"=="0" goto installer_failed
if /i "%STATE%"=="done" exit /b 0
if /i "%STATE%"=="idle" exit /b 0
if /i "%STATE%"=="cancelled" exit /b 0
if /i "%STATE%"=="failed" goto installer_failed
goto installer_unexpected_close

:installer_unexpected_close
echo.
echo [ERRO] O hub fechou inesperadamente durante a etapa: %STATE%
echo [ERRO] O hub fechou inesperadamente durante a etapa: %STATE%>>"%LAUNCHLOG%"
"%PS%" -NoProfile -ExecutionPolicy Bypass -Command "try { Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show(('O hub fechou inesperadamente durante a etapa: %STATE%' + [Environment]::NewLine + [Environment]::NewLine + 'Veja logs\install.log e logs\install-launcher.log'), 'Neve AI - Hub', 'OK', 'Error') | Out-Null } catch {}" >nul 2>nul
pause
exit /b 1

:installer_failed
echo.
echo [ERRO] O hub falhou. Veja logs\install.log e logs\install-launcher.log
echo [ERRO] O hub falhou com codigo %RC%; estado=%STATE%.>>"%LAUNCHLOG%"
"%PS%" -NoProfile -ExecutionPolicy Bypass -Command "try { Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show(('O hub falhou.' + [Environment]::NewLine + [Environment]::NewLine + 'Estado: %STATE%' + [Environment]::NewLine + 'Codigo: %RC%' + [Environment]::NewLine + [Environment]::NewLine + 'Veja logs\install.log e logs\install-launcher.log'), 'Neve AI - Hub', 'OK', 'Error') | Out-Null } catch {}" >nul 2>nul
pause
exit /b 1
