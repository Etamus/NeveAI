param(
	[switch]$ValidateOnly,
	[switch]$DebugConsole
)

$ErrorActionPreference = 'Stop'

$LauncherDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $LauncherDir
$Backend = Join-Path $Root 'backend'
$VenvPy = Join-Path $Root 'backend\neveai\venv\Scripts\python.exe'
$VenvPyw = Join-Path $Root 'backend\neveai\venv\Scripts\pythonw.exe'
$WindowScript = Join-Path $Root 'neve_window.py'
$WindowIconPath = Join-Path $Root 'static\static\faviconbar.ico'
$LogDir = Join-Path $Root 'logs'
$LogPath = Join-Path $LogDir 'start-launcher.log'

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-StartLog {
	param([string]$Message)
	$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'
	Add-Content -LiteralPath $LogPath -Value "[$stamp] $Message"
}

function Quote-PsLiteral {
	param([string]$Value)
	return $Value.Replace("'", "''")
}

function Resolve-LogoPath {
	$candidates = @(
		(Join-Path $Root 'static\static\favicon.png'),
		(Join-Path $Root 'static\static\logo.png'),
		(Join-Path $Root 'build\static\favicon.png'),
		(Join-Path $Root 'backend\neveai\static\favicon.png')
	)

	foreach ($candidate in $candidates) {
		if (Test-Path -LiteralPath $candidate) {
			return $candidate
		}
	}

	return $null
}

function Pump-Ui {
	$frame = New-Object System.Windows.Threading.DispatcherFrame
	$callback = [System.Windows.Threading.DispatcherOperationCallback]{
		param($Frame)
		$Frame.Continue = $false
		return $null
	}
	[System.Windows.Threading.Dispatcher]::CurrentDispatcher.BeginInvoke(
		[System.Windows.Threading.DispatcherPriority]::Background,
		$callback,
		$frame
	) | Out-Null
	[System.Windows.Threading.Dispatcher]::PushFrame($frame)
}

function Show-Error {
	param([string]$Message)
	[System.Windows.MessageBox]::Show($Message, 'NeveAI', 'OK', 'Error') | Out-Null
}

Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase
Add-Type @'
using System;
using System.Runtime.InteropServices;

public static class NeveLauncherWindowIdentity
{
    private const uint WM_SETICON = 0x0080;
    private const int ICON_SMALL = 0;
    private const int ICON_BIG = 1;
    private const int ICON_SMALL2 = 2;
    private const uint IMAGE_ICON = 1;
    private const uint LR_LOADFROMFILE = 0x0010;
    private const uint LR_DEFAULTSIZE = 0x0040;

    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    public static extern int SetCurrentProcessExplicitAppUserModelID(string appId);

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr LoadImage(
        IntPtr instance,
        string name,
        uint type,
        int width,
        int height,
        uint loadFlags
    );

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr SendMessage(IntPtr window, uint message, IntPtr wParam, IntPtr lParam);

    public static void ApplyIcon(IntPtr window, string iconPath)
    {
        IntPtr icon = LoadImage(
            IntPtr.Zero,
            iconPath,
            IMAGE_ICON,
            0,
            0,
            LR_LOADFROMFILE | LR_DEFAULTSIZE
        );
        if (icon == IntPtr.Zero) return;

        SendMessage(window, WM_SETICON, new IntPtr(ICON_BIG), icon);
        SendMessage(window, WM_SETICON, new IntPtr(ICON_SMALL), icon);
        SendMessage(window, WM_SETICON, new IntPtr(ICON_SMALL2), icon);
    }
}
'@

[NeveLauncherWindowIdentity]::SetCurrentProcessExplicitAppUserModelID('NeveAI.Startup') | Out-Null

$logoPath = Resolve-LogoPath
$xaml = @'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Width="430"
        Height="245"
        WindowStartupLocation="CenterScreen"
        WindowStyle="None"
        ResizeMode="NoResize"
        AllowsTransparency="True"
        Background="Transparent"
        Topmost="True"
        ShowInTaskbar="True">
    <Border Background="White"
            BorderBrush="#E5E7EB"
            BorderThickness="1"
            CornerRadius="14"
            Padding="30">
        <Border.Effect>
            <DropShadowEffect BlurRadius="28" ShadowDepth="0" Opacity="0.22" Color="#111827" />
        </Border.Effect>
        <Grid>
            <Grid.RowDefinitions>
                <RowDefinition Height="*" />
                <RowDefinition Height="Auto" />
            </Grid.RowDefinitions>

            <StackPanel Grid.Row="0"
                        HorizontalAlignment="Center"
                        VerticalAlignment="Center"
                        Orientation="Vertical">
                <StackPanel HorizontalAlignment="Center"
                            Orientation="Horizontal"
                            Margin="0,0,0,18">
                    <Image x:Name="Logo"
                           Width="84"
                           Height="84"
                           Stretch="Uniform"
                           Margin="-25,3,0,0" />
                    <TextBlock Text="NeveAI"
                               VerticalAlignment="Center"
                               Foreground="#111827"
                               FontSize="38"
                               FontWeight="SemiBold" />
                </StackPanel>
                <TextBlock x:Name="StatusText"
                           Text="Iniciando..."
                           HorizontalAlignment="Center"
                           Foreground="#6B7280"
                           FontSize="12"
                           Margin="10,20,0,0" />
            </StackPanel>

            <Grid Grid.Row="1">
                <ProgressBar x:Name="Progress"
                             Height="6"
                             Minimum="0"
                             Maximum="100"
                             Value="0"
                             Foreground="#111827"
                             Background="#E5E7EB"
                             BorderThickness="0" />
            </Grid>
        </Grid>
    </Border>
</Window>
'@

$reader = New-Object System.Xml.XmlNodeReader ([xml]$xaml)
$window = [Windows.Markup.XamlReader]::Load($reader)
$logo = $window.FindName('Logo')
$statusText = $window.FindName('StatusText')
$progressBar = $window.FindName('Progress')

if (Test-Path -LiteralPath $WindowIconPath) {
	$window.Icon = [System.Windows.Media.Imaging.BitmapFrame]::Create([Uri]$WindowIconPath)
	$window.Add_SourceInitialized({
		$interop = New-Object System.Windows.Interop.WindowInteropHelper($window)
		[NeveLauncherWindowIdentity]::ApplyIcon($interop.Handle, $WindowIconPath)
	})
}

$window.Add_MouseLeftButtonDown({
	param($sender, $eventArgs)
	if ($eventArgs.ButtonState -eq 'Pressed') {
		try { $window.DragMove() } catch {}
	}
})

if ($logoPath) {
	$image = New-Object System.Windows.Media.Imaging.BitmapImage
	$image.BeginInit()
	$image.UriSource = [Uri]$logoPath
	$image.CacheOption = [System.Windows.Media.Imaging.BitmapCacheOption]::OnLoad
	$image.EndInit()
	$logo.Source = $image
}

function Set-SplashProgress {
	param(
		[string]$Text,
		[int]$Value
	)
	$statusText.Text = $Text
	$progressBar.Value = [Math]::Max(0, [Math]::Min(100, $Value))
	Pump-Ui
}

if ($ValidateOnly) {
	exit 0
}

try {
	Write-StartLog "launcher started; root=$Root"
	$window.Show()
	$window.Activate() | Out-Null

	Set-SplashProgress 'Preparando ambiente...' 8

	if (-not (Test-Path -LiteralPath $VenvPy)) {
		throw 'Ambiente Python nao encontrado. Execute instalar.bat primeiro.'
	}
	if (-not (Test-Path -LiteralPath (Join-Path $Backend 'neveai\models\users.py'))) {
		throw 'Arquivos do backend incompletos. Execute instalar.bat para reparar a instalacao.'
	}
	if (-not (Test-Path -LiteralPath $WindowScript)) {
		throw 'Arquivo neve_window.py nao encontrado.'
	}

	Set-SplashProgress 'Encerrando processos anteriores...' 22
	$owners = @(
		Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue |
			Where-Object { $_.OwningProcess -and $_.OwningProcess -ne 0 } |
			Select-Object -ExpandProperty OwningProcess -Unique
	)
	foreach ($owner in $owners) {
		Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
	}

	Set-SplashProgress 'Iniciando backend...' 40
	if ($DebugConsole) {
		$backendQ = Quote-PsLiteral $Backend
		$venvPyQ = Quote-PsLiteral $VenvPy
		$backendCommand = "`$env:PYTHONIOENCODING='utf-8'; `$env:PYTHONPATH='$backendQ'; Set-Location -LiteralPath '$backendQ'; & '$venvPyQ' -m uvicorn neveai.main:app --host 0.0.0.0 --port 8080"
		$cmdStartCommand = 'start "NeveAI - Backend" /min /D "' + $Backend + '" powershell -NoProfile -ExecutionPolicy Bypass -Command "' + $backendCommand.Replace('"', '\"') + '"'
		Start-Process -FilePath 'cmd.exe' -ArgumentList @('/c', $cmdStartCommand) -WindowStyle Hidden -WorkingDirectory $Root | Out-Null
		Write-StartLog 'backend debug console started through cmd start /min'
	} else {
		$backendOutLog = Join-Path $LogDir 'backend.log'
		$backendErrorLog = Join-Path $LogDir 'backend-error.log'
		$previousPythonEncoding = $env:PYTHONIOENCODING
		$previousPythonPath = $env:PYTHONPATH
		try {
			$env:PYTHONIOENCODING = 'utf-8'
			$env:PYTHONPATH = $Backend
			$backendProcess = Start-Process -FilePath $VenvPy `
				-ArgumentList @('-m', 'uvicorn', 'neveai.main:app', '--host', '0.0.0.0', '--port', '8080') `
				-WorkingDirectory $Backend `
				-WindowStyle Hidden `
				-RedirectStandardOutput $backendOutLog `
				-RedirectStandardError $backendErrorLog `
				-PassThru
			Write-StartLog "backend started without console; pid=$($backendProcess.Id); stdout=$backendOutLog; stderr=$backendErrorLog"
		} finally {
			$env:PYTHONIOENCODING = $previousPythonEncoding
			$env:PYTHONPATH = $previousPythonPath
		}
	}

	Set-SplashProgress 'Aguardando backend...' 52
	$start = [DateTime]::UtcNow
	while ($true) {
		try {
			$request = [System.Net.HttpWebRequest]::Create('http://127.0.0.1:8080/health')
			$request.Timeout = 500
			$request.Method = 'GET'
			$response = $request.GetResponse()
			$response.Close()
			break
		} catch {
			$elapsed = ([DateTime]::UtcNow - $start).TotalSeconds
			if ($elapsed -gt 120) {
				throw 'Backend nao respondeu em 120 segundos.'
			}

			$progress = 52 + [int]([Math]::Min(42, ($elapsed / 120) * 42))
			$status = if ($elapsed -gt 10) { 'Carregando dependencias...' } else { 'Aguardando backend...' }
			Set-SplashProgress $status $progress
			Start-Sleep -Milliseconds 250
		}
	}

	Set-SplashProgress 'Abrindo NeveAI...' 100

	$pythonWindow = if (Test-Path -LiteralPath $VenvPyw) { $VenvPyw } else { $VenvPy }
	$readyFile = Join-Path $LogDir ("webview-ready-{0}.tmp" -f $PID)
	Remove-Item -LiteralPath $readyFile -Force -ErrorAction SilentlyContinue
	$previousReadyFile = $env:NEVE_WINDOW_READY_FILE
	try {
		$env:NEVE_WINDOW_READY_FILE = $readyFile
		$frontendProcess = Start-Process -FilePath $pythonWindow -ArgumentList @("`"$WindowScript`"") -WorkingDirectory $Root -PassThru
	} finally {
		$env:NEVE_WINDOW_READY_FILE = $previousReadyFile
	}

	$readyDeadline = [DateTime]::UtcNow.AddSeconds(12)
	while (-not (Test-Path -LiteralPath $readyFile) -and [DateTime]::UtcNow -lt $readyDeadline) {
		if ($frontendProcess.HasExited) { break }
		Pump-Ui
		Start-Sleep -Milliseconds 40
	}
	Remove-Item -LiteralPath $readyFile -Force -ErrorAction SilentlyContinue

	$window.Close()
	$window = $null
	Write-StartLog "frontend window opened; launcher pid=$($frontendProcess.Id)"
} catch {
	Write-StartLog "[FATAL] $($_.Exception.Message)"
	if ($window) {
		$window.Close()
	}
	Show-Error $_.Exception.Message
}
