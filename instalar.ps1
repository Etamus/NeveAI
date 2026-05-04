# Neve AI - Instalador Grafico (WPF)
# UI bonita + progresso visual + log em tempo real.
# Toda a logica original (deteccao de GPU, llama.cpp, venv, requirements, npm)
# roda em runspace separado para nao travar a interface.

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding           = [Console]::OutputEncoding
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls11 -bor [Net.SecurityProtocolType]::Tls
} catch {
    try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}
}

Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase
Add-Type -AssemblyName System.Windows.Forms

# =============================================================================
# Caminhos globais
# =============================================================================
$SCRIPT_PATH = if ($PSCommandPath) { $PSCommandPath } elseif ($MyInvocation.MyCommand.Path) { $MyInvocation.MyCommand.Path } else { throw 'Não foi possível determinar o caminho do instalador.' }
$ROOT        = (Resolve-Path -LiteralPath (Split-Path -Parent $SCRIPT_PATH)).ProviderPath
Set-Location -LiteralPath $ROOT
$VENV_DIR = Join-Path $ROOT 'backend\neveai\venv'
$VENV_PY  = Join-Path $VENV_DIR 'Scripts\python.exe'
$BACKEND  = Join-Path $ROOT 'backend'
$LOG_DIR  = Join-Path $ROOT 'logs'
if (-not (Test-Path $LOG_DIR)) { New-Item $LOG_DIR -ItemType Directory | Out-Null }
$LOG = Join-Path $LOG_DIR 'install.log'
$STATE_FILE = Join-Path $LOG_DIR 'install-state.txt'
'' | Set-Content $LOG
[System.IO.File]::WriteAllText($STATE_FILE, 'idle', [System.Text.UTF8Encoding]::new($false))

# Logo (favicon do projeto)
$LOGO_PATH = Join-Path $ROOT 'static\favicon.png'
if (-not (Test-Path $LOGO_PATH)) {
    $LOGO_PATH = Join-Path $ROOT 'static\static\favicon.png'
}

# =============================================================================
# XAML - Interface
# =============================================================================
[xml]$xaml = @"
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Neve AI - Instalador"
        Width="780" Height="560"
        WindowStartupLocation="CenterScreen"
        ResizeMode="NoResize"
        WindowStyle="None"
        AllowsTransparency="True"
        Background="Transparent">
    <Window.Resources>
        <Style x:Key="PrimaryBtn" TargetType="Button">
            <Setter Property="Background" Value="#111111"/>
            <Setter Property="Foreground" Value="White"/>
            <Setter Property="BorderThickness" Value="0"/>
            <Setter Property="Padding" Value="22,9"/>
            <Setter Property="FontSize" Value="13"/>
            <Setter Property="FontWeight" Value="SemiBold"/>
            <Setter Property="Cursor" Value="Hand"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="Button">
                        <Border x:Name="bd" Background="{TemplateBinding Background}" CornerRadius="8" Padding="{TemplateBinding Padding}">
                            <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
                        </Border>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="bd" Property="Background" Value="#262626"/>
                            </Trigger>
                            <Trigger Property="IsEnabled" Value="False">
                                <Setter TargetName="bd" Property="Opacity" Value="0.4"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>
        <Style x:Key="GhostBtn" TargetType="Button" BasedOn="{StaticResource PrimaryBtn}">
            <Setter Property="Background" Value="#F4F4F5"/>
            <Setter Property="Foreground" Value="#111111"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="Button">
                        <Border x:Name="bd" Background="{TemplateBinding Background}" CornerRadius="8" Padding="{TemplateBinding Padding}">
                            <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
                        </Border>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="bd" Property="Background" Value="#E4E4E7"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>
        <Style TargetType="ComboBox">
            <Setter Property="FontSize" Value="13"/>
            <Setter Property="Padding" Value="8,4"/>
        </Style>
    </Window.Resources>

    <Border CornerRadius="14" Background="#FAFAFA" BorderBrush="#E4E4E7" BorderThickness="1">
        <Grid>
            <Grid.RowDefinitions>
                <RowDefinition Height="56"/>
                <RowDefinition Height="*"/>
                <RowDefinition Height="68"/>
            </Grid.RowDefinitions>

            <!-- TITLE BAR -->
            <Grid Grid.Row="0" Background="Transparent">
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="Auto"/>
                    <ColumnDefinition Width="*"/>
                    <ColumnDefinition Width="Auto"/>
                </Grid.ColumnDefinitions>
                <StackPanel Grid.Column="0" Orientation="Horizontal" Margin="18,0,0,0" VerticalAlignment="Center">
                    <Image x:Name="LogoImg" Width="22" Height="22" Margin="0,0,10,0"/>
                    <TextBlock Text="Neve AI" FontSize="15" FontWeight="SemiBold" Foreground="#111111" VerticalAlignment="Center"/>
                    <TextBlock Text="  ·  Instalador" FontSize="13" Foreground="#71717A" VerticalAlignment="Center"/>
                </StackPanel>
                <Button x:Name="BtnClose" Grid.Column="2" Width="44" Height="32" Margin="0,0,12,0"
                        Background="Transparent" BorderThickness="0" Cursor="Hand">
                    <Button.Template>
                        <ControlTemplate TargetType="Button">
                            <Border x:Name="bd" Background="Transparent" CornerRadius="6">
                                <TextBlock Text="X" FontSize="13" Foreground="#71717A" HorizontalAlignment="Center" VerticalAlignment="Center"/>
                            </Border>
                            <ControlTemplate.Triggers>
                                <Trigger Property="IsMouseOver" Value="True">
                                    <Setter TargetName="bd" Property="Background" Value="#E4E4E7"/>
                                </Trigger>
                            </ControlTemplate.Triggers>
                        </ControlTemplate>
                    </Button.Template>
                </Button>
            </Grid>

            <!-- BODY (cards swap by visibility) -->
            <Grid Grid.Row="1" Margin="32,8,32,0">

                <!-- WELCOME / CONFIG CARD -->
                <Grid x:Name="ConfigPanel">
                    <Grid.RowDefinitions>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="*"/>
                    </Grid.RowDefinitions>

                    <StackPanel Grid.Row="0" Margin="0,0,0,18">
                        <TextBlock Text="Bem-vindo a Neve AI" FontSize="22" FontWeight="SemiBold" Foreground="#111111"/>
                        <TextBlock Text="Vamos detectar seu hardware e instalar tudo o que é preciso."
                                   FontSize="13" Foreground="#71717A" Margin="0,4,0,0"/>
                    </StackPanel>

                    <Border Grid.Row="1" Background="White" CornerRadius="10" BorderBrush="#E4E4E7" BorderThickness="1" Padding="20">
                        <Grid>
                            <Grid.ColumnDefinitions>
                                <ColumnDefinition Width="220"/>
                                <ColumnDefinition Width="*"/>
                            </Grid.ColumnDefinitions>
                            <Grid.RowDefinitions>
                                <RowDefinition Height="Auto"/>
                                <RowDefinition Height="Auto"/>
                                <RowDefinition Height="Auto"/>
                                <RowDefinition Height="Auto"/>
                                <RowDefinition Height="Auto"/>
                            </Grid.RowDefinitions>

                            <TextBlock Grid.Row="0" Grid.Column="0" Text="GPU detectada:" FontSize="13" Foreground="#52525B" Margin="0,0,0,12"/>
                            <TextBlock Grid.Row="0" Grid.Column="1" x:Name="LblGpu" Text="Detectando..." FontSize="13" FontWeight="SemiBold" Foreground="#111111" Margin="0,0,0,12" TextTrimming="CharacterEllipsis"/>

                            <TextBlock Grid.Row="1" Grid.Column="0" Text="Tipo de aceleração:" FontSize="13" Foreground="#52525B" Margin="0,0,0,12"/>
                            <ComboBox  Grid.Row="1" Grid.Column="1" x:Name="CmbBackend" Margin="0,0,0,12">
                                <ComboBoxItem Content="CPU (sem GPU)"/>
                                <ComboBoxItem Content="NVIDIA - RTX 50xx (Blackwell, CUDA 13)"/>
                                <ComboBoxItem Content="NVIDIA - RTX 40xx (Ada, CUDA 12.8)"/>
                                <ComboBoxItem Content="NVIDIA - RTX 30xx (Ampere, CUDA 12.8)"/>
                                <ComboBoxItem Content="NVIDIA - RTX 20xx (Turing, CUDA 12.6)"/>
                                <ComboBoxItem Content="NVIDIA - GTX 16xx (Turing, CUDA 12.4)"/>
                                <ComboBoxItem Content="NVIDIA - GTX 10xx ou anterior (Pascal)"/>
                                <ComboBoxItem Content="NVIDIA - Profissional (RTX A/Quadro/Tesla)"/>
                                <ComboBoxItem Content="AMD - HIP/ROCm 6.3"/>
                                <ComboBoxItem Content="AMD - Vulkan"/>
                            </ComboBox>

                            <TextBlock Grid.Row="2" Grid.Column="0" Text="VRAM (GB):" FontSize="13" Foreground="#52525B" Margin="0,0,0,12"/>
                            <ComboBox  Grid.Row="2" Grid.Column="1" x:Name="CmbVram" Margin="0,0,0,12">
                                <ComboBoxItem Content="Pular"/>
                                <ComboBoxItem Content="4 GB"/>
                                <ComboBoxItem Content="6 GB"/>
                                <ComboBoxItem Content="8 GB"/>
                                <ComboBoxItem Content="12 GB"/>
                                <ComboBoxItem Content="16 GB"/>
                                <ComboBoxItem Content="24 GB"/>
                                <ComboBoxItem Content="32 GB ou mais"/>
                            </ComboBox>

                            <TextBlock Grid.Row="3" Grid.Column="0" Text="Flash Attention (Opcional):" FontSize="13" Foreground="#52525B" Margin="0,0,0,12"/>
                            <CheckBox  Grid.Row="3" Grid.Column="1" x:Name="ChkFlash" Content="Compilar Flash Attention (requer CUDA Toolkit + MSVC Build Tools)" FontSize="13" Margin="0,2,0,12"/>

                            <Border Grid.Row="4" Grid.ColumnSpan="2" Background="#FAFAFA" CornerRadius="8" Padding="14,12" Margin="0,8,0,0">
                                <StackPanel>
                                    <TextBlock Text="O que será instalado:" FontWeight="SemiBold" FontSize="13" Foreground="#111111" Margin="0,0,0,4"/>
                                    <TextBlock Text="• llama.cpp (binários mais recentes do GitHub)" FontSize="12" Foreground="#52525B"/>
                                    <TextBlock Text="• Python venv com PyTorch + diffusers + dependências do backend" FontSize="12" Foreground="#52525B"/>
                                    <TextBlock Text="• Pacotes npm e build do frontend" FontSize="12" Foreground="#52525B"/>
                                    <TextBlock Text="• Estrutura de pastas (logs, models, mmproj, data) e .env padrão" FontSize="12" Foreground="#52525B"/>
                                </StackPanel>
                            </Border>
                        </Grid>
                    </Border>
                </Grid>

                <!-- INSTALL CARD -->
                <Grid x:Name="InstallPanel" Visibility="Collapsed">
                    <Grid.RowDefinitions>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="*"/>
                    </Grid.RowDefinitions>

                    <StackPanel Grid.Row="0" Margin="0,0,0,12">
                        <TextBlock Text="Instalando..." FontSize="22" FontWeight="SemiBold" Foreground="#111111"/>
                        <TextBlock x:Name="LblStep" Text="Preparando…" FontSize="13" Foreground="#71717A" Margin="0,4,0,0"/>
                    </StackPanel>

                    <Border Grid.Row="1" Background="White" CornerRadius="10" BorderBrush="#E4E4E7" BorderThickness="1" Padding="16,14" Margin="0,0,0,14">
                        <StackPanel>
                            <Grid>
                                <TextBlock x:Name="LblProgressTxt" Text="0%" FontSize="12" Foreground="#52525B" HorizontalAlignment="Right"/>
                                <TextBlock x:Name="LblPhase" Text="Iniciando" FontSize="12" Foreground="#52525B"/>
                            </Grid>
                            <ProgressBar x:Name="Progress" Height="6" Minimum="0" Maximum="100" Value="0" Margin="0,8,0,0"
                                         Foreground="#111111" Background="#F4F4F5" BorderThickness="0"/>
                        </StackPanel>
                    </Border>

                    <Border Grid.Row="2" Background="#0A0A0A" CornerRadius="10" Padding="14,12">
                        <ScrollViewer x:Name="LogScroll" VerticalScrollBarVisibility="Auto">
                            <TextBox x:Name="LogBox" Background="Transparent" Foreground="#D4D4D4" BorderThickness="0"
                                     IsReadOnly="True" FontFamily="Consolas" FontSize="11" TextWrapping="Wrap"
                                     AcceptsReturn="True" VerticalScrollBarVisibility="Disabled"/>
                        </ScrollViewer>
                    </Border>
                </Grid>

                <!-- DONE CARD -->
                <Grid x:Name="DonePanel" Visibility="Collapsed">
                    <Border Background="White" CornerRadius="10" BorderBrush="#E4E4E7" BorderThickness="1" Padding="32">
                        <StackPanel HorizontalAlignment="Center" VerticalAlignment="Center">
                            <Border Width="56" Height="56" CornerRadius="28" Background="#10B981" Margin="0,0,0,18">
                                <TextBlock Text="OK" FontSize="20" FontWeight="Bold" Foreground="White" HorizontalAlignment="Center" VerticalAlignment="Center"/>
                            </Border>
                            <TextBlock x:Name="LblDoneTitle" Text="Tudo pronto!" FontSize="22" FontWeight="SemiBold" Foreground="#111111" HorizontalAlignment="Center"/>
                            <TextBlock x:Name="LblDoneSub" Text="Use start.bat para iniciar o Neve AI." FontSize="13" Foreground="#71717A" HorizontalAlignment="Center" Margin="0,6,0,18"/>
                            <Border Background="#FAFAFA" CornerRadius="8" Padding="14,12">
                                <TextBlock x:Name="LblSummary" FontFamily="Consolas" FontSize="11" Foreground="#52525B"/>
                            </Border>
                        </StackPanel>
                    </Border>
                </Grid>

            </Grid>

            <!-- FOOTER -->
            <Border Grid.Row="2" BorderBrush="#EEEEEE" BorderThickness="0,1,0,0" Padding="32,0,32,0">
                <StackPanel Orientation="Horizontal" HorizontalAlignment="Right" VerticalAlignment="Center">
                    <Button x:Name="BtnCancel" Style="{StaticResource GhostBtn}" Content="Cancelar" Margin="0,0,10,0"/>
                    <Button x:Name="BtnPrimary" Style="{StaticResource PrimaryBtn}" Content="Instalar"/>
                </StackPanel>
            </Border>
        </Grid>
    </Border>
</Window>
"@

# =============================================================================
# Carregar XAML
# =============================================================================
$reader = New-Object System.Xml.XmlNodeReader $xaml
$window = [Windows.Markup.XamlReader]::Load($reader)
$window.Tag = 'idle'

# Atalhos para controles
$ctl = @{}
foreach ($name in 'LogoImg','BtnClose','LblGpu','CmbBackend','CmbVram','ChkFlash',
                  'ConfigPanel','InstallPanel','DonePanel',
                  'LblStep','LblPhase','LblProgressTxt','Progress','LogBox','LogScroll',
                  'LblDoneTitle','LblDoneSub','LblSummary',
                  'BtnCancel','BtnPrimary') {
    $ctl[$name] = $window.FindName($name)
}

$window.Dispatcher.add_UnhandledException({
    param($sender, $eventArgs)
    $msg = if ($eventArgs.Exception) { $eventArgs.Exception.Message } else { 'Falha inesperada no instalador.' }
    try { [System.IO.File]::WriteAllText($STATE_FILE, 'failed', [System.Text.UTF8Encoding]::new($false)) } catch {}
    try { Add-Content -LiteralPath $LOG -Value "[FATAL UI] $msg" -Encoding UTF8 } catch {}
    try {
        $ctl.LblStep.Text = 'Falha inesperada no instalador.'
        $ctl.LblPhase.Text = 'Falha inesperada no instalador.'
        $ctl.BtnPrimary.IsEnabled = $true
        $ctl.BtnPrimary.Content = 'Fechar'
        $ctl.BtnPrimary.Tag = 'done'
        $ctl.BtnCancel.IsEnabled = $true
        $ctl.BtnClose.IsEnabled = $true
        $window.Tag = 'failed'
        $ctl.LogBox.AppendText("[FATAL UI] $msg`r`n")
        $ctl.LogScroll.ScrollToEnd()
    } catch {}
    [System.Windows.MessageBox]::Show("O instalador encontrou uma falha, mas a janela ficará aberta.`n`nVeja logs\install.log`n`n$msg", 'Neve AI - Instalador', 'OK', 'Error') | Out-Null
    $eventArgs.Handled = $true
})

# Logo
if (Test-Path $LOGO_PATH) {
    try {
        $bmp = New-Object System.Windows.Media.Imaging.BitmapImage
        $bmp.BeginInit()
        $bmp.UriSource = New-Object System.Uri($LOGO_PATH, [System.UriKind]::Absolute)
        $bmp.CacheOption = [System.Windows.Media.Imaging.BitmapCacheOption]::OnLoad
        $bmp.EndInit()
        $ctl.LogoImg.Source = $bmp
    } catch {}
}

# Drag da janela
$window.Add_MouseLeftButtonDown({
    param($s, $e)
    if ($e.ButtonState -eq 'Pressed') { try { $window.DragMove() } catch {} }
})

# Botoes basicos
$ctl.BtnClose.Add_Click({ $window.Close() })
$ctl.BtnCancel.Add_Click({ $window.Close() })
$window.Add_Closing({
    param($sender, $eventArgs)
    if ([string]$window.Tag -eq 'installing') {
        $eventArgs.Cancel = $true
        [System.Windows.MessageBox]::Show(
            'A instalação está em andamento. A janela não será fechada até concluir ou falhar com log visível.',
            'Neve AI - Instalador', 'OK', 'Information') | Out-Null
    }
})

# =============================================================================
# Deteccao de hardware (executa antes de mostrar a janela)
# =============================================================================
$detected = @{
    Vendor    = 'CPU'
    Name      = ''
    Backend   = 0   # indice do CmbBackend
}

try {
    $nOut = nvidia-smi --query-gpu=name --format=csv,noheader 2>&1
    if ($LASTEXITCODE -eq 0 -and "$nOut" -notmatch 'failed|not found') {
        $detected.Vendor = 'NVIDIA'
        $detected.Name   = ("$nOut" -split "`n")[0].Trim()
    }
} catch {}

if ($detected.Vendor -eq 'CPU') {
    try {
        $gpus = Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name -EA SilentlyContinue
        $amdGpu = $gpus | Where-Object { $_ -match 'AMD|Radeon|RX\s' } | Select-Object -First 1
        if ($amdGpu) {
            $detected.Vendor = 'AMD'
            $detected.Name   = $amdGpu.Trim()
        }
    } catch {}
}

# Mapear deteccao para indice do dropdown
if ($detected.Vendor -eq 'NVIDIA') {
    $n = $detected.Name
    if     ($n -match 'RTX\s*5\d{3}|50\d{2}')                      { $detected.Backend = 1 }
    elseif ($n -match 'RTX\s*4\d{3}|40\d{2}')                      { $detected.Backend = 2 }
    elseif ($n -match 'RTX\s*3\d{3}|30\d{2}')                      { $detected.Backend = 3 }
    elseif ($n -match 'RTX\s*2\d{3}|20\d{2}')                      { $detected.Backend = 4 }
    elseif ($n -match 'GTX\s*16\d{2}')                             { $detected.Backend = 5 }
    elseif ($n -match 'GTX\s*10\d{2}|GTX\s*9\d{2}|GTX\s*7\d{2}')   { $detected.Backend = 6 }
    elseif ($n -match 'RTX\s*A|Quadro|Tesla')                      { $detected.Backend = 7 }
    else                                                            { $detected.Backend = 2 }
} elseif ($detected.Vendor -eq 'AMD') {
    $detected.Backend = 9   # Vulkan default (mais compativel no Windows)
}

function Test-PythonLaunch([string]$exe, [string[]]$prefixArgs = @()) {
    try {
        if ([string]::IsNullOrWhiteSpace($exe) -or -not (Test-Path -LiteralPath $exe)) { return $null }
        $fullExe = (Resolve-Path -LiteralPath $exe).ProviderPath
        if ($fullExe -match '\\Microsoft\\WindowsApps\\python(3)?\.exe$') { return $null }

        $probe = 'import sys, venv, ensurepip; print(sys.executable); print(sys.version.split()[0])'
        $output = & $fullExe @prefixArgs -c $probe 2>&1
        if ($LASTEXITCODE -ne 0) { return $null }

        $lines = @($output | ForEach-Object { "$_".Trim() } | Where-Object { $_ })
        if ($lines.Count -lt 2) { return $null }

        $realExe = $lines[0]
        $version = $lines[-1]
        if (-not (Test-Path -LiteralPath $realExe)) { $realExe = $fullExe }

        $parts = $version -split '\.'
        if ($parts.Count -lt 2 -or $parts[0] -ne '3' -or @('11','12') -notcontains $parts[1]) {
            return $null
        }

        [pscustomobject]@{
            Executable = (Resolve-Path -LiteralPath $realExe).ProviderPath
            Version    = $version
        }
    } catch {
        return $null
    }
}

function Resolve-PythonLaunch {
    $candidates = @()

    foreach ($cmd in @(Get-Command py.exe -All -EA SilentlyContinue)) {
        foreach ($versionArg in @('-3.12', '-3.11')) {
            $candidates += [pscustomobject]@{ Exe = $cmd.Source; Args = @($versionArg) }
        }
    }

    foreach ($name in @('python.exe', 'python3.exe')) {
        foreach ($cmd in @(Get-Command $name -All -EA SilentlyContinue)) {
            $candidates += [pscustomobject]@{ Exe = $cmd.Source; Args = @() }
        }
    }

    $pythonRoots = @($env:LocalAppData, $env:ProgramFiles, ${env:ProgramFiles(x86)}, 'C:\') | Where-Object { $_ }
    foreach ($root in $pythonRoots) {
        foreach ($minor in @('312', '311')) {
            foreach ($relative in @("Programs\Python\Python$minor\python.exe", "Python$minor\python.exe")) {
                $path = Join-Path $root $relative
                if (Test-Path -LiteralPath $path) { $candidates += [pscustomobject]@{ Exe = $path; Args = @() } }
            }
        }
    }

    $seen = @{}
    foreach ($candidate in $candidates) {
        $key = "$($candidate.Exe)|$($candidate.Args -join ' ')"
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true

        $resolved = Test-PythonLaunch $candidate.Exe ([string[]]$candidate.Args)
        if ($resolved) { return $resolved }
    }

    return $null
}

function Test-NodeLaunch([string]$exe) {
    try {
        if ([string]::IsNullOrWhiteSpace($exe) -or -not (Test-Path -LiteralPath $exe)) { return $null }
        $fullExe = (Resolve-Path -LiteralPath $exe).ProviderPath
        if ($fullExe -match '\\Microsoft\\WindowsApps\\node\.exe$') { return $null }

        $versionOut = & $fullExe --version 2>&1
        if ($LASTEXITCODE -ne 0) { return $null }
        $version = (("$versionOut" -split "`r?`n") | Where-Object { $_.Trim() } | Select-Object -First 1).Trim()
        if ($version -notmatch '^v?(\d+)\.') { return $null }
        if ([int]$matches[1] -lt 18) { return $null }

        [pscustomobject]@{
            Executable = $fullExe
            Version    = $version
        }
    } catch {
        return $null
    }
}

function Test-NpmLaunch([string]$exe) {
    try {
        if ([string]::IsNullOrWhiteSpace($exe) -or -not (Test-Path -LiteralPath $exe)) { return $null }
        $fullExe = (Resolve-Path -LiteralPath $exe).ProviderPath
        $versionOut = & $fullExe --version 2>&1
        if ($LASTEXITCODE -ne 0) { return $null }
        $version = (("$versionOut" -split "`r?`n") | Where-Object { $_.Trim() } | Select-Object -First 1).Trim()
        if (-not $version) { return $null }

        [pscustomobject]@{
            Executable = $fullExe
            Version    = $version
        }
    } catch {
        return $null
    }
}

function Resolve-NodeLaunch {
    $nodeCandidates = @()
    foreach ($cmd in @(Get-Command node.exe -All -EA SilentlyContinue)) {
        $nodeCandidates += $cmd.Source
    }

    foreach ($nodeBase in (@($env:ProgramFiles, ${env:ProgramFiles(x86)}) | Where-Object { $_ })) {
        $path = Join-Path $nodeBase 'nodejs\node.exe'
        if (Test-Path -LiteralPath $path) { $nodeCandidates += $path }
    }

    $npmCandidates = @()
    foreach ($name in @('npm.cmd', 'npm.exe', 'npm')) {
        foreach ($cmd in @(Get-Command $name -All -EA SilentlyContinue)) {
            $npmCandidates += $cmd.Source
        }
    }

    foreach ($nodeCandidate in ($nodeCandidates | Select-Object -Unique)) {
        $nodeDir = Split-Path -Parent $nodeCandidate
        foreach ($npmName in @('npm.cmd', 'npm.exe')) {
            $npmPath = Join-Path $nodeDir $npmName
            if (Test-Path -LiteralPath $npmPath) { $npmCandidates += $npmPath }
        }
    }

    foreach ($nodeCandidate in ($nodeCandidates | Select-Object -Unique)) {
        $node = Test-NodeLaunch $nodeCandidate
        if (-not $node) { continue }

        foreach ($npmCandidate in ($npmCandidates | Select-Object -Unique)) {
            $npm = Test-NpmLaunch $npmCandidate
            if ($npm) {
                return [pscustomobject]@{
                    NodeExecutable = $node.Executable
                    NodeVersion    = $node.Version
                    NpmExecutable  = $npm.Executable
                    NpmVersion     = $npm.Version
                }
            }
        }
    }

    return $null
}

# Pre-checar Python e Node
$pythonLaunch = Resolve-PythonLaunch
$pyOk = $null -ne $pythonLaunch
$PYTHON_EXE = if ($pyOk) { $pythonLaunch.Executable } else { $null }
$pyVer = if ($pyOk) { "Python $($pythonLaunch.Version)" } else { '' }
$nodeLaunch = Resolve-NodeLaunch
$nodeOk = $null -ne $nodeLaunch
$NODE_EXE = if ($nodeOk) { $nodeLaunch.NodeExecutable } else { $null }
$NPM_EXE = if ($nodeOk) { $nodeLaunch.NpmExecutable } else { $null }
$nodeVer = if ($nodeOk) { "$($nodeLaunch.NodeVersion) / npm $($nodeLaunch.NpmVersion)" } else { '' }

if ($detected.Name) {
    $ctl.LblGpu.Text = $detected.Name
} else {
    $ctl.LblGpu.Text = "Nenhuma GPU detectada (modo CPU)"
}
$ctl.CmbBackend.SelectedIndex = $detected.Backend
$ctl.CmbVram.SelectedIndex    = 0
$ctl.ChkFlash.IsChecked       = $false

# Se faltar Python ou Node, bloqueia o botao
if (-not $pyOk -or -not $nodeOk) {
    $ctl.BtnPrimary.IsEnabled = $false
    $ctl.BtnPrimary.Content   = 'Pré-requisitos faltando'
    $missing = @()
    if (-not $pyOk)   { $missing += 'Python 3.11 ou 3.12 real, com venv/ensurepip (desative aliases Python da Microsoft Store se necessário)' }
    if (-not $nodeOk) { $missing += 'Node.js 18+ com npm (https://nodejs.org)' }
    [System.Windows.MessageBox]::Show(
        "Faltando:`n  • " + ($missing -join "`n  • ") + "`n`nInstale e abra o instalador novamente.",
        'Pré-requisitos', 'OK', 'Warning') | Out-Null
}

# =============================================================================
# Funcoes auxiliares de UI (chamadas via Dispatcher)
# =============================================================================
function UI-Invoke([scriptblock]$sb) {
    $window.Dispatcher.Invoke([Action]$sb)
}

function UI-Log([string]$msg, [string]$kind='info') {
    UI-Invoke {
        $color = switch ($kind) {
            'ok'    { '[OK] ' }
            'warn'  { '[!]  ' }
            'err'   { '[X]  ' }
            'step'  { '==>  ' }
            default { '     ' }
        }
        $line = "$color$msg`r`n"
        $ctl.LogBox.AppendText($line)
        $ctl.LogScroll.ScrollToEnd()
    }
}

function UI-Progress([int]$val, [string]$phase) {
    UI-Invoke {
        $ctl.Progress.Value     = $val
        $ctl.LblProgressTxt.Text = "$val%"
        if ($phase) { $ctl.LblPhase.Text = $phase; $ctl.LblStep.Text = $phase }
    }
}

function ConvertTo-ProcessArgument([string]$arg) {
    if ($null -eq $arg) { throw 'Argumento nulo.' }
    if ($arg.Length -gt 0 -and $arg -notmatch '[\s"]') { return $arg }
    $escaped = [regex]::Replace($arg, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function Run-Logged([string]$exe, [string[]]$args, [string]$desc) {
    UI-Log $desc 'info'
    if ([string]::IsNullOrWhiteSpace($exe)) {
        throw "Executável vazio ao executar '$desc'."
    }

    $safeArgs = @()
    foreach ($a in @($args)) {
        if ($null -eq $a) {
            throw "Argumento nulo ao executar '$desc' com '$exe'."
        }
        $safeArgs += [string]$a
    }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $processExe = $exe
    $processArgs = (($safeArgs | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' ')
    $extension = [System.IO.Path]::GetExtension($exe)
    if (@('.cmd', '.bat') -contains $extension.ToLowerInvariant()) {
        $cmdExe = if ($env:ComSpec -and (Test-Path -LiteralPath $env:ComSpec)) { $env:ComSpec } else { Join-Path $env:SystemRoot 'System32\cmd.exe' }
        $processExe = $cmdExe
        $quote = [char]34
        $cmdCommand = $quote + ($exe -replace $quote, ($quote + $quote)) + $quote
        if ($safeArgs.Count -gt 0) { $cmdCommand += ' ' + (($safeArgs | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' ') }
        $processArgs = '/d /s /c ' + $quote + $cmdCommand + $quote
    }

    $psi.FileName               = $processExe
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true
    $psi.UseShellExecute        = $false
    $psi.CreateNoWindow         = $true
    $psi.Arguments              = $processArgs
    $cmdLine = "CMD: {0} {1}" -f $exe, ($safeArgs -join ' ')
    UI-Log $cmdLine 'info'
    Add-Content $LOG $cmdLine

    $queue = New-Object 'System.Collections.Concurrent.ConcurrentQueue[string]'
    $stdoutHandler = [System.Diagnostics.DataReceivedEventHandler]{
        param($sender, $eventArgs)
        if ($null -ne $eventArgs.Data -and $eventArgs.Data.Length -gt 0) {
            $queue.Enqueue($eventArgs.Data)
        }
    }
    $stderrHandler = [System.Diagnostics.DataReceivedEventHandler]{
        param($sender, $eventArgs)
        if ($null -ne $eventArgs.Data -and $eventArgs.Data.Length -gt 0) {
            $queue.Enqueue($eventArgs.Data)
        }
    }

    function Drain-RunLoggedOutput {
        $line = $null
        while ($queue.TryDequeue([ref]$line)) {
            UI-Log $line 'info'
            Add-Content $LOG $line
            $line = $null
        }
    }

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    [void]$proc.add_OutputDataReceived($stdoutHandler)
    [void]$proc.add_ErrorDataReceived($stderrHandler)

    try {
        [void]$proc.Start()
        UI-Log ("[pid {0}] {1} iniciado" -f $proc.Id, $desc) 'info'
        $startedAt = Get-Date
        $lastHeartbeat = $startedAt

        $proc.BeginOutputReadLine()
        $proc.BeginErrorReadLine()

        while (-not $proc.WaitForExit(250)) {
            Drain-RunLoggedOutput
            $now = Get-Date
            if (($now - $lastHeartbeat).TotalSeconds -ge 30) {
                $elapsedMin = [math]::Max(1, [math]::Floor(($now - $startedAt).TotalMinutes))
                $line = "... {0} ainda em andamento ({1} min). Aguardando processo responder." -f $desc, $elapsedMin
                UI-Log $line 'info'
                Add-Content $LOG $line
                $lastHeartbeat = $now
            }
        }

        $proc.WaitForExit()
        Drain-RunLoggedOutput

        $elapsed = (Get-Date) - $startedAt
        $line = "[exit {0}] {1} finalizado em {2:mm\:ss}" -f $proc.ExitCode, $desc, $elapsed
        UI-Log $line 'info'
        Add-Content $LOG $line
        return $proc.ExitCode
    } finally {
        try { $proc.CancelOutputRead() } catch {}
        try { $proc.CancelErrorRead() } catch {}
        try { $proc.remove_OutputDataReceived($stdoutHandler) } catch {}
        try { $proc.remove_ErrorDataReceived($stderrHandler) } catch {}
        $proc.Dispose()
    }
}

# =============================================================================
# Worker - executa em runspace separado
# =============================================================================
$ctl.BtnPrimary.Add_Click({
    if ($ctl.BtnPrimary.Tag -eq 'done') { $window.Close(); return }
    if ([string]::IsNullOrWhiteSpace($PYTHON_EXE) -or -not (Test-Path -LiteralPath $PYTHON_EXE)) {
        [System.Windows.MessageBox]::Show(
            "Python 3.11/3.12 válido não encontrado. Instale pelo python.org e desative aliases Python da Microsoft Store, se existirem.",
            'Neve AI - Instalador', 'OK', 'Warning') | Out-Null
        return
    }
    if ([string]::IsNullOrWhiteSpace($NODE_EXE) -or -not (Test-Path -LiteralPath $NODE_EXE) -or [string]::IsNullOrWhiteSpace($NPM_EXE) -or -not (Test-Path -LiteralPath $NPM_EXE)) {
        [System.Windows.MessageBox]::Show(
            "Node.js 18+ com npm não encontrado. Instale pelo nodejs.org e abra o instalador novamente.",
            'Neve AI - Instalador', 'OK', 'Warning') | Out-Null
        return
    }

    # Coleta selecoes
    $backendIdx  = $ctl.CmbBackend.SelectedIndex
    $vramIdx     = $ctl.CmbVram.SelectedIndex
    $flashAttn   = [bool]$ctl.ChkFlash.IsChecked

    $vramMap     = @(0,4,6,8,12,16,24,32)
    $vramGb      = $vramMap[$vramIdx]

    # Mapeia indice -> torchIndex / llamaAsset / cudaVer / useOnnxGpu
    $cfg = switch ($backendIdx) {
        0 { @{ torchIndex='https://download.pytorch.org/whl/cpu'; llamaAsset='cpu';        cudaVer='CPU';                 useOnnxGpu=$false; vendor='CPU'    } }
        1 { @{ torchIndex='https://download.pytorch.org/whl/cu128'; llamaAsset='cuda-13.1'; cudaVer='CUDA 13.1 (Blackwell)'; useOnnxGpu=$true;  vendor='NVIDIA' } }
        2 { @{ torchIndex='https://download.pytorch.org/whl/cu128'; llamaAsset='cuda-12.4'; cudaVer='CUDA 12.8 (Ada)';        useOnnxGpu=$true;  vendor='NVIDIA' } }
        3 { @{ torchIndex='https://download.pytorch.org/whl/cu128'; llamaAsset='cuda-12.4'; cudaVer='CUDA 12.8 (Ampere)';     useOnnxGpu=$true;  vendor='NVIDIA' } }
        4 { @{ torchIndex='https://download.pytorch.org/whl/cu126'; llamaAsset='cuda-12.4'; cudaVer='CUDA 12.6 (Turing)';     useOnnxGpu=$true;  vendor='NVIDIA' } }
        5 { @{ torchIndex='https://download.pytorch.org/whl/cu124'; llamaAsset='cuda-12.4'; cudaVer='CUDA 12.4 (Turing)';     useOnnxGpu=$true;  vendor='NVIDIA' } }
        6 { @{ torchIndex='https://download.pytorch.org/whl/cu124'; llamaAsset='cuda-12.4'; cudaVer='CUDA 12.4 (Pascal)';     useOnnxGpu=$false; vendor='NVIDIA' } }
        7 { @{ torchIndex='https://download.pytorch.org/whl/cu128'; llamaAsset='cuda-12.4'; cudaVer='CUDA 12.8 (Profissional)'; useOnnxGpu=$true; vendor='NVIDIA' } }
        8 { @{ torchIndex='https://download.pytorch.org/whl/cpu'; llamaAsset='hip-radeon'; cudaVer='AMD HIP/ROCm (PyTorch CPU no Windows)'; useOnnxGpu=$false; vendor='AMD'    } }
        9 { @{ torchIndex='https://download.pytorch.org/whl/cpu'; llamaAsset='vulkan';         cudaVer='Vulkan';              useOnnxGpu=$false; vendor='AMD'    } }
        default { @{ torchIndex='https://download.pytorch.org/whl/cpu'; llamaAsset='cpu'; cudaVer='CPU'; useOnnxGpu=$false; vendor='CPU' } }
    }

    # Trocar para a tela de instalacao
    $window.Tag = 'installing'
    try { [System.IO.File]::WriteAllText($STATE_FILE, 'running', [System.Text.UTF8Encoding]::new($false)) } catch {}
    $ctl.ConfigPanel.Visibility = 'Collapsed'
    $ctl.InstallPanel.Visibility = 'Visible'
    $ctl.BtnPrimary.IsEnabled = $false
    $ctl.BtnCancel.IsEnabled  = $false
    $ctl.BtnClose.IsEnabled = $false

    # ---- Atalho: se TUDO ja esta instalado, marca como concluido
    $venvOk     = Test-Path $VENV_PY
    $torchOk    = $false
    if ($venvOk) {
        try {
            & $VENV_PY -c "import torch, fastapi, transformers" 2>&1 | Out-Null
            $torchOk = ($LASTEXITCODE -eq 0)
        } catch { $torchOk = $false }
    }
    $llamaOk    = (Get-ChildItem (Join-Path $ROOT 'llamacpp-server\bin') -Filter '*.exe' -EA SilentlyContinue | Measure-Object).Count -gt 0
    $nodeModsOk = Test-Path (Join-Path $ROOT 'node_modules')
    $frontendOk = Test-Path (Join-Path $BACKEND 'neveai\frontend\index.html')
    $envOk      = Test-Path (Join-Path $ROOT '.env')

    if ($venvOk -and $torchOk -and $llamaOk -and $nodeModsOk -and $frontendOk -and $envOk) {
        $ctl.LogBox.AppendText("[OK] Tudo já está instalado. Nada a fazer.`r`n")
        $ctl.Progress.Value      = 100
        $ctl.LblProgressTxt.Text = '100%'
        $ctl.LblPhase.Text       = 'Concluído'
        $ctl.LblStep.Text        = 'Concluído'

        $summary = @()
        $summary += "Python:      $((& $PYTHON_EXE --version 2>&1))"
        $summary += "Node.js:     $((& $NODE_EXE --version 2>&1))"
        try {
            $tOut = & $VENV_PY -c "import torch; v=torch.__version__; cuda='(CUDA '+torch.version.cuda+')' if torch.cuda.is_available() else '(CPU)'; print('PyTorch '+v+' '+cuda)" 2>$null
            if ($tOut) { $summary += "PyTorch:     $tOut" }
        } catch {}
        if ($vramGb -gt 0) { $summary += "VRAM:        ${vramGb} GB ($($detected.Name))" }

        $ctl.InstallPanel.Visibility = 'Collapsed'
        $ctl.DonePanel.Visibility    = 'Visible'
        $ctl.LblDoneTitle.Text       = 'Já está tudo pronto!'
        $ctl.LblDoneSub.Text         = 'Nenhuma pendência detectada. Use start.bat para iniciar o Neve AI.'
        $ctl.LblSummary.Text         = ($summary -join "`r`n")
        $ctl.BtnCancel.Visibility    = 'Collapsed'
        $ctl.BtnPrimary.IsEnabled    = $true
        $ctl.BtnPrimary.Content      = 'Concluir'
        $ctl.BtnPrimary.Tag          = 'done'
        $window.Tag = 'done'
        try { [System.IO.File]::WriteAllText($STATE_FILE, 'done', [System.Text.UTF8Encoding]::new($false)) } catch {}
        return
    }

    # Worker em runspace separado, usando as funcoes UI-* via $window
    $worker = {
        param($cfg, $flashAttn, $vramGb, $detected, $ROOT, $VENV_DIR, $VENV_PY, $BACKEND, $LOG, $STATE_FILE, $PYTHON_EXE, $NODE_EXE, $NPM_EXE)

        # Helpers (definidas dentro do runspace)
        function Log([string]$m, [string]$k='info') {
            $line = if ($null -eq $m) { '' } else { [string]$m }
            try {
                if ($script:Window -and $script:Ctl -and $script:Ctl.LogBox) {
                    $script:Window.Dispatcher.Invoke([Action]{
                        $script:Ctl.LogBox.AppendText("$line`r`n")
                        $script:Ctl.LogScroll.ScrollToEnd()
                    })
                }
            } catch {}
            Add-Content $LOG $line
        }
        function P([int]$v, [string]$phase) {
            try {
                if ($script:Window -and $script:Ctl) {
                    $script:Window.Dispatcher.Invoke([Action]{
                        $script:Ctl.Progress.Value = $v
                        $script:Ctl.LblProgressTxt.Text = "$v%"
                        if ($phase) { $script:Ctl.LblPhase.Text = $phase; $script:Ctl.LblStep.Text = $phase }
                    })
                }
            } catch {}
        }
        function Set-InstallState([string]$state) {
            try { [System.IO.File]::WriteAllText($STATE_FILE, $state, [System.Text.UTF8Encoding]::new($false)) } catch {}
        }
        function ConvertTo-ProcessArgument([string]$arg) {
            if ($null -eq $arg) { throw 'Argumento nulo.' }
            if ($arg.Length -gt 0 -and $arg -notmatch '[\s"]') { return $arg }
            $escaped = [regex]::Replace($arg, '(\\*)"', '$1$1\"')
            $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
            return '"' + $escaped + '"'
        }
        function Run([string]$exe, [string[]]$argv, [string]$desc) {
            Log "==> $desc"
            if ([string]::IsNullOrWhiteSpace($exe)) {
                throw "Executável vazio ao executar '$desc'."
            }

            $safeArgs = @()
            foreach ($a in @($argv)) {
                if ($null -eq $a) {
                    throw "Argumento nulo ao executar '$desc' com '$exe'."
                }
                $safeArgs += [string]$a
            }

            $psi = New-Object System.Diagnostics.ProcessStartInfo
            $processExe = $exe
            $processArgs = (($safeArgs | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' ')
            $extension = [System.IO.Path]::GetExtension($exe)
            if (@('.cmd', '.bat') -contains $extension.ToLowerInvariant()) {
                $cmdExe = if ($env:ComSpec -and (Test-Path -LiteralPath $env:ComSpec)) { $env:ComSpec } else { Join-Path $env:SystemRoot 'System32\cmd.exe' }
                $processExe = $cmdExe
                $quote = [char]34
                $cmdCommand = $quote + ($exe -replace $quote, ($quote + $quote)) + $quote
                if ($safeArgs.Count -gt 0) { $cmdCommand += ' ' + (($safeArgs | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' ') }
                $processArgs = '/d /s /c ' + $quote + $cmdCommand + $quote
            }

            $psi.FileName = $processExe
            $psi.RedirectStandardOutput = $true
            $psi.RedirectStandardError  = $true
            $psi.UseShellExecute = $false
            $psi.CreateNoWindow  = $true
            $psi.Arguments = $processArgs
            Log ("CMD: {0} {1}" -f $exe, ($safeArgs -join ' '))

            $queue = New-Object 'System.Collections.Concurrent.ConcurrentQueue[string]'
            $stdoutHandler = [System.Diagnostics.DataReceivedEventHandler]{
                param($sender, $eventArgs)
                if ($null -ne $eventArgs.Data -and $eventArgs.Data.Length -gt 0) {
                    $queue.Enqueue($eventArgs.Data)
                }
            }
            $stderrHandler = [System.Diagnostics.DataReceivedEventHandler]{
                param($sender, $eventArgs)
                if ($null -ne $eventArgs.Data -and $eventArgs.Data.Length -gt 0) {
                    $queue.Enqueue($eventArgs.Data)
                }
            }

            function Drain-RunOutput {
                $line = $null
                while ($queue.TryDequeue([ref]$line)) {
                    Log $line
                    $line = $null
                }
            }

            $p = $null
            try {
                $p = New-Object System.Diagnostics.Process
                $p.StartInfo = $psi
                [void]$p.add_OutputDataReceived($stdoutHandler)
                [void]$p.add_ErrorDataReceived($stderrHandler)
                [void]$p.Start()
                Log ("[pid {0}] {1} iniciado" -f $p.Id, $desc)
            } catch {
                throw "Falha ao iniciar '$exe' para '$desc': $($_.Exception.Message)"
            }
            if ($null -eq $p) {
                throw "Falha ao iniciar '$exe' para '$desc': Process.Start retornou nulo."
            }

            try {
                $startedAt = Get-Date
                $lastHeartbeat = $startedAt

                $p.BeginOutputReadLine()
                $p.BeginErrorReadLine()

                while (-not $p.WaitForExit(250)) {
                    Drain-RunOutput
                    $now = Get-Date
                    if (($now - $lastHeartbeat).TotalSeconds -ge 30) {
                        $elapsedMin = [math]::Max(1, [math]::Floor(($now - $startedAt).TotalMinutes))
                        Log ("... {0} ainda em andamento ({1} min). Aguardando pip/processo responder." -f $desc, $elapsedMin)
                        $lastHeartbeat = $now
                    }
                }

                $p.WaitForExit()
                Drain-RunOutput

                $elapsed = (Get-Date) - $startedAt
                Log ("[exit {0}] {1} finalizado em {2:mm\:ss}" -f $p.ExitCode, $desc, $elapsed)
                return $p.ExitCode
            } finally {
                try { $p.CancelOutputRead() } catch {}
                try { $p.CancelErrorRead() } catch {}
                try { $p.remove_OutputDataReceived($stdoutHandler) } catch {}
                try { $p.remove_ErrorDataReceived($stderrHandler) } catch {}
                $p.Dispose()
            }
        }
        function Run-NoPipe([string]$exe, [string[]]$argv, [string]$desc) {
            Log "==> $desc"
            if ([string]::IsNullOrWhiteSpace($exe)) { throw "Executável vazio ao executar '$desc'." }

            $safeArgs = @()
            foreach ($a in @($argv)) {
                if ($null -eq $a) { throw "Argumento nulo ao executar '$desc' com '$exe'." }
                $safeArgs += [string]$a
            }

            $psi = New-Object System.Diagnostics.ProcessStartInfo
            $psi.FileName = $exe
            $psi.Arguments = (($safeArgs | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' ')
            $psi.WorkingDirectory = $ROOT
            $psi.RedirectStandardOutput = $false
            $psi.RedirectStandardError = $false
            $psi.UseShellExecute = $false
            $psi.CreateNoWindow = $true
            Log ("CMD: {0} {1}" -f $exe, ($safeArgs -join ' '))

            $p = $null
            try {
                $p = New-Object System.Diagnostics.Process
                $p.StartInfo = $psi
                [void]$p.Start()
                Log ("[pid {0}] {1} iniciado (sem pipes de stdout/stderr para evitar fechamento do WPF no venv)" -f $p.Id, $desc)
            } catch {
                throw "Falha ao iniciar '$exe' para '$desc': $($_.Exception.Message)"
            }
            if ($null -eq $p) { throw "Falha ao iniciar '$exe' para '$desc': Process.Start retornou nulo." }

            try {
                $startedAt = Get-Date
                $lastHeartbeat = $startedAt
                while (-not $p.WaitForExit(1000)) {
                    $now = Get-Date
                    if (($now - $lastHeartbeat).TotalSeconds -ge 10) {
                        $elapsedSec = [math]::Floor(($now - $startedAt).TotalSeconds)
                        Log ("... {0} ainda em andamento ({1}s)." -f $desc, $elapsedSec)
                        $lastHeartbeat = $now
                    }
                }
                $p.WaitForExit()
                $elapsed = (Get-Date) - $startedAt
                Log ("[exit {0}] {1} finalizado em {2:mm\:ss}" -f $p.ExitCode, $desc, $elapsed)
                return $p.ExitCode
            } finally {
                try { $p.Dispose() } catch {}
            }
        }
        function Run([string]$exe, [string[]]$argv, [string]$desc) {
            return Run-NoPipe $exe $argv $desc
        }
        function Test-CommandExists([string]$name) {
            return $null -ne (Get-Command $name -EA SilentlyContinue)
        }
        function Test-MsvcBuildTools {
            if (Test-CommandExists 'cl.exe') { return $true }

            $vswhereCandidates = @()
            foreach ($vsBase in (@(${env:ProgramFiles(x86)}, $env:ProgramFiles) | Where-Object { $_ })) {
                $vswherePath = Join-Path $vsBase 'Microsoft Visual Studio\Installer\vswhere.exe'
                if (Test-Path -LiteralPath $vswherePath) { $vswhereCandidates += $vswherePath }
            }

            foreach ($vswhere in $vswhereCandidates) {
                try {
                    $installPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>$null
                    if ($installPath) { return $true }
                } catch {}
            }

            return $false
        }
        function Get-RequirementEntries([string]$path) {
            $entries = @()
            $lines = Get-Content -LiteralPath $path
            for ($i = 0; $i -lt $lines.Count; $i++) {
                $line = ([string]$lines[$i]).Trim()
                if (-not $line -or $line.StartsWith('#')) { continue }
                $line = [regex]::Replace($line, '\s+#.*$', '').Trim()
                if (-not $line) { continue }
                $entries += [pscustomobject]@{
                    Line = $i + 1
                    Spec = $line
                }
            }
            return $entries
        }

        try {
            Set-Location -LiteralPath $ROOT
            Log "[OK] Pasta de instalação: $ROOT"

            # ---- 1. Estrutura de pastas
            P 5 'Criando estrutura de pastas'
            foreach ($d in @('logs','logs\webview2','logs\browser-app','models','mmproj',
                             'backend\data','backend\data\uploads','backend\data\vector_db',
                             'backend\data\cache','backend\data\tools',
                             'backend\neveai\frontend')) {
                $p = Join-Path $ROOT $d
                if (-not (Test-Path $p)) { New-Item $p -ItemType Directory -Force | Out-Null }
            }
            Log "[OK] Pastas garantidas"

            # ---- 2. .env padrao
            $envPath = Join-Path $ROOT '.env'
            if (-not (Test-Path -LiteralPath $envPath)) {
                $envText = @"
VITE_RELATIVE_CONFIG=True
VITE_NEVEAI_BACKEND_URL=http://localhost:8080
ENV=dev
PORT=8080
NEVE_SECRET_KEY=troque-esta-chave-por-algo-seguro
NEVE_AUTH=False
NEVE_NAME=Neve AI
ENABLE_OLLAMA_API=False
ENABLE_OPENAI_API=False
ENABLE_WEB_SEARCH=False
ENABLE_IMAGE_GENERATION=False
ENABLE_WEBSOCKET_SUPPORT=True
ENABLE_COMMUNITY_SHARING=False
ENABLE_MESSAGE_RATING=False
BYPASS_MODEL_ACCESS_CONTROL=True
ENABLE_SIGNUP=True
ENABLE_LOGIN_FORM=True
SAFE_MODE=False
CORS_ALLOW_ORIGIN=http://localhost:8080
USER_AGENT=Neve AI
"@
                [System.IO.File]::WriteAllText($envPath, $envText, [System.Text.UTF8Encoding]::new($false))
                Log "[OK] .env criado"
            } else {
                Log "[…] .env preservado"
            }

            # ---- 3. llama.cpp
            P 12 'Baixando llama.cpp'
            $llamaDir = Join-Path $ROOT 'llamacpp-server\bin'
            if (-not (Test-Path (Split-Path $llamaDir -Parent))) { New-Item (Split-Path $llamaDir -Parent) -ItemType Directory | Out-Null }
            if (-not (Test-Path $llamaDir)) { New-Item $llamaDir -ItemType Directory | Out-Null }
            $llamaServer = Join-Path $llamaDir 'llama-server.exe'
            $llamaInstalled = $false
            try {
                $rel = Invoke-RestMethod 'https://api.github.com/repos/ggml-org/llama.cpp/releases/latest' -Headers @{ 'User-Agent' = 'Neve-Installer/3.0' } -TimeoutSec 60
                $tag = $rel.tag_name
                if (-not $tag) { throw 'Release do llama.cpp sem tag_name.' }

                $attempts = @($cfg.llamaAsset, 'cpu') | Where-Object { $_ } | Select-Object -Unique
                foreach ($assetName in $attempts) {
                    $tmpFiles = @(); $stageDir = $null; $backupDir = $null
                    try {
                        $binName = "llama-$tag-bin-win-$assetName-x64.zip"
                        $binObj  = $rel.assets | Where-Object { $_.name -eq $binName } | Select-Object -First 1
                        if (-not $binObj) { throw "Asset $binName não encontrado." }

                        $stageDir = Join-Path $env:TEMP "neve_llama_stage_$([guid]::NewGuid().ToString('N'))"
                        New-Item $stageDir -ItemType Directory -Force | Out-Null

                        $sizeMB = [math]::Round($binObj.size/1MB,0)
                        Log "==> Baixando $binName ($sizeMB MB)"
                        $tmpBin = Join-Path $env:TEMP "neve_llama_bin_$([guid]::NewGuid().ToString('N')).zip"
                        $tmpFiles += $tmpBin
                        Invoke-WebRequest $binObj.browser_download_url -OutFile $tmpBin -UseBasicParsing -Headers @{ 'User-Agent' = 'Neve-Installer/3.0' } -TimeoutSec 300
                        Expand-Archive $tmpBin -DestinationPath $stageDir -Force

                        if ($assetName -match '^cuda-') {
                            P 18 'Baixando CUDA Runtime'
                            $dllName = "cudart-llama-bin-win-$assetName-x64.zip"
                            $dllObj  = $rel.assets | Where-Object { $_.name -eq $dllName } | Select-Object -First 1
                            if (-not $dllObj) { throw "Runtime CUDA $dllName não encontrado." }
                            $sizeMB = [math]::Round($dllObj.size/1MB,0)
                            Log "==> Baixando $dllName ($sizeMB MB)"
                            $tmpDll = Join-Path $env:TEMP "neve_cudart_$([guid]::NewGuid().ToString('N')).zip"
                            $tmpFiles += $tmpDll
                            Invoke-WebRequest $dllObj.browser_download_url -OutFile $tmpDll -UseBasicParsing -Headers @{ 'User-Agent' = 'Neve-Installer/3.0' } -TimeoutSec 300
                            Expand-Archive $tmpDll -DestinationPath $stageDir -Force
                        }

                        $serverExe = Get-ChildItem $stageDir -Recurse -File -Filter 'llama-server.exe' | Select-Object -First 1
                        if (-not $serverExe) { throw "O pacote $binName não contém llama-server.exe." }
                        $stagedFiles = @(Get-ChildItem $stageDir -Recurse -File)
                        if ($stagedFiles.Count -eq 0) { throw "O pacote $binName não extraiu arquivos." }

                        $backupDir = Join-Path $env:TEMP "neve_llama_backup_$([guid]::NewGuid().ToString('N'))"
                        New-Item $backupDir -ItemType Directory -Force | Out-Null
                        Get-ChildItem $llamaDir -Force -EA SilentlyContinue | ForEach-Object { Copy-Item $_.FullName $backupDir -Recurse -Force }

                        try {
                            Get-Process llama-server -EA SilentlyContinue | Stop-Process -Force -EA SilentlyContinue
                            Get-ChildItem $llamaDir -File -EA SilentlyContinue | Where-Object { $_.Extension -in '.exe','.dll','.pdb' } | Remove-Item -Force -EA Stop
                            foreach ($file in $stagedFiles) { Copy-Item $file.FullName $llamaDir -Force -EA Stop }
                            if (-not (Test-Path -LiteralPath $llamaServer)) { throw 'llama-server.exe não ficou disponível após a cópia.' }
                        } catch {
                            $applyError = $_
                            Log "[!] Falha ao aplicar llama.cpp; restaurando backup: $applyError" 'warn'
                            try {
                                Get-ChildItem $llamaDir -Force -EA SilentlyContinue | Remove-Item -Recurse -Force -EA SilentlyContinue
                                Get-ChildItem $backupDir -Force -EA SilentlyContinue | ForEach-Object { Copy-Item $_.FullName $llamaDir -Recurse -Force }
                            } catch {}
                            throw $applyError
                        }

                        Set-Content -Path (Join-Path (Split-Path $llamaDir -Parent) 'version.txt') -Value @($tag, $assetName, $binName) -Encoding UTF8
                        Log "[OK] llama.cpp $tag instalado ($assetName)"
                        $llamaInstalled = $true
                        break
                    } catch {
                        if ($assetName -ne 'cpu') { Log "[!] Falha ao instalar llama.cpp ${assetName}: $_. Tentando CPU." 'warn' } else { Log "[!] Falha ao instalar llama.cpp CPU: $_" 'warn' }
                    } finally {
                        foreach ($tmp in $tmpFiles) { try { Remove-Item $tmp -Force -EA SilentlyContinue } catch {} }
                        if ($stageDir) { try { Remove-Item $stageDir -Recurse -Force -EA SilentlyContinue } catch {} }
                        if ($backupDir) { try { Remove-Item $backupDir -Recurse -Force -EA SilentlyContinue } catch {} }
                    }
                }
            } catch {
                Log "[!] Falha ao consultar release do llama.cpp: $_" 'warn'
            }
            if (-not $llamaInstalled -and -not (Test-Path -LiteralPath $llamaServer)) {
                throw 'Não foi possível instalar o llama.cpp e nenhum llama-server.exe existente foi encontrado. Verifique a conexão com a internet e tente novamente.'
            }
            if (-not $llamaInstalled) { Log '[!] Usando llama.cpp existente porque o download novo não pôde ser concluído.' 'warn' }

            # ---- 4. Recriar venv
            P 25 'Recriando ambiente Python'
            if ([string]::IsNullOrWhiteSpace($PYTHON_EXE) -or -not (Test-Path -LiteralPath $PYTHON_EXE)) {
                throw "Python 3.11/3.12 válido não encontrado para criar o venv. Instale pelo python.org e desative aliases Python da Microsoft Store, se existirem."
            }
            Set-InstallState 'creating_venv'
            Log "[OK] Python selecionado: $PYTHON_EXE"
            if (Test-Path $VENV_DIR) {
                Log "==> Removendo venv antigo"
                try { Remove-Item $VENV_DIR -Recurse -Force -EA Stop } catch {
                    Log "[X] Falha ao remover venv: $_" 'err'; throw
                }
            }
            $venvParent = Split-Path -Parent $VENV_DIR
            if (-not (Test-Path -LiteralPath $venvParent)) { New-Item -ItemType Directory -Path $venvParent -Force | Out-Null }
            $rc = Run-NoPipe $PYTHON_EXE @('-m','venv',$VENV_DIR) 'Criando venv'
            if ($rc -ne 0) {
                Log "[!] Criação padrão do venv falhou (exit $rc). Tentando novamente com --copies." 'warn'
                if (Test-Path $VENV_DIR) { Remove-Item $VENV_DIR -Recurse -Force -EA SilentlyContinue }
                $rc = Run-NoPipe $PYTHON_EXE @('-m','venv','--copies',$VENV_DIR) 'Criando venv (--copies)'
            }
            if ($rc -ne 0) { throw "Falha ao criar venv (exit $rc). Python usado: $PYTHON_EXE. Pasta alvo: $VENV_DIR" }
            if (-not (Test-Path $VENV_PY)) {
                throw "O venv foi criado, mas o Python interno não foi encontrado em '$VENV_PY'. Verifique se o Python instalado suporta venv e se o antivírus não bloqueou a criação dos executáveis."
            }
            Set-InstallState 'venv_created'
            Log "[OK] venv criado"

            # ---- 5. pip + PyTorch
            Set-InstallState 'installing_python_packages'
            $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
            $env:PIP_NO_INPUT = '1'
            $env:PIP_DEFAULT_TIMEOUT = '60'
            $env:PIP_PROGRESS_BAR = 'raw'
            $env:PYTHONUNBUFFERED = '1'
            $pipLog = Join-Path (Split-Path -Parent $LOG) 'pip-install.log'
            try { [System.IO.File]::WriteAllText($pipLog, '', [System.Text.UTF8Encoding]::new($false)) } catch {}
            Log "[OK] Log detalhado do pip: $pipLog"
            $pipInstall = @('-m','pip','--log',$pipLog,'install','--disable-pip-version-check','--no-input','--prefer-binary','--progress-bar','off','--retries','5','--timeout','60')

            P 32 'Atualizando pip'
            Set-InstallState 'pip_upgrade'
            [void](Run $VENV_PY ($pipInstall + @('--upgrade','pip')) 'pip upgrade')

            P 38 "Instalando PyTorch ($($cfg.cudaVer))"
            Set-InstallState 'installing_torch'
            $rc = Run $VENV_PY ($pipInstall + @('torch','torchvision','--index-url',$cfg.torchIndex)) 'PyTorch + torchvision'
            if ($rc -ne 0) { throw "Falha ao instalar PyTorch (exit $rc)" }
            Log "[OK] PyTorch instalado"

            # ---- 6. Flash Attention (opcional)
            if ($flashAttn -and $cfg.vendor -eq 'NVIDIA') {
                if (-not (Test-CommandExists 'nvcc.exe')) {
                    Log "[!] Flash Attention Python ignorado: requer CUDA Toolkit completo (nvcc.exe). O llama.cpp e o Neve AI funcionam normalmente sem esse pacote." 'warn'
                } elseif (-not (Test-MsvcBuildTools)) {
                    Log "[!] Flash Attention Python ignorado: requer MSVC Build Tools. O llama.cpp e o Neve AI funcionam normalmente sem esse pacote." 'warn'
                } else {
                    P 48 'Compilando Flash Attention Python (~10 min)'
                    Set-InstallState 'installing_flash_attn'
                    $rc = Run $VENV_PY ($pipInstall + @('flash-attn','--no-build-isolation')) 'flash-attn'
                    if ($rc -eq 0) {
                        Log "[OK] Flash Attention Python instalado"
                    } else {
                        Log "[!] Flash Attention Python falhou (opcional). O llama.cpp e o Neve AI funcionam normalmente sem esse pacote." 'warn'
                    }
                }
            }

            # ---- 7. diffusers
            P 55 'Instalando diffusers'
            Set-InstallState 'installing_diffusers'
            Log "==> diffusers será instalado separadamente para facilitar diagnóstico"
            [void](Run $VENV_PY ($pipInstall + @('diffusers')) 'diffusers')

            # ---- 8. requirements do backend
            P 60 'Instalando dependências do backend (~5-15 min)'
            Set-InstallState 'installing_backend_requirements'
            $runtimeReq = Join-Path $BACKEND 'requirements-runtime.txt'
            $fullReq = Join-Path $BACKEND 'requirements.txt'
            $useFullReq = @('1','true','yes','sim') -contains ([string]$env:NEVE_INSTALL_FULL_REQUIREMENTS).ToLowerInvariant()
            if ((-not $useFullReq) -and (Test-Path -LiteralPath $runtimeReq)) {
                $req = $runtimeReq
                Log "[OK] Usando requirements-runtime.txt (dependências essenciais do Neve AI)"
                Log "    Para instalar a lista completa antiga, defina NEVE_INSTALL_FULL_REQUIREMENTS=1 antes de abrir o instalador."
            } else {
                $req = $fullReq
                Log "[OK] Usando requirements.txt completo"
            }
            if (-not (Test-Path -LiteralPath $req)) {
                throw "Arquivo de dependências não encontrado em '$req'."
            }
            $reqName = Split-Path -Leaf $req
            $reqEntries = @(Get-RequirementEntries $req)
            $reqCount = $reqEntries.Count
            Log "[OK] $reqName encontrado: $reqCount entradas"
            Log "==> Instalando $reqName pacote por pacote para mostrar progresso e identificar qualquer travamento"
            $failedRequirements = @()
            for ($i = 0; $i -lt $reqEntries.Count; $i++) {
                $entry = $reqEntries[$i]
                $index = $i + 1
                $percent = 60 + [math]::Floor(($index / [math]::Max(1, $reqCount)) * 17)
                P $percent ("{0} {1}/{2}" -f $reqName, $index, $reqCount)
                Set-InstallState ("installing_requirement_{0}_of_{1}" -f $index, $reqCount)
                Log ("==> {0} [{1}/{2}] linha {3}: {4}" -f $reqName, $index, $reqCount, $entry.Line, $entry.Spec)
                $rc = Run $VENV_PY ($pipInstall + @($entry.Spec)) ("{0} {1}/{2}: {3}" -f $reqName, $index, $reqCount, $entry.Spec)
                if ($rc -ne 0) {
                    $failedRequirements += ("linha {0}: {1} (exit {2})" -f $entry.Line, $entry.Spec, $rc)
                    Log ("[X] Falha em {0} linha {1}: {2} (exit {3})" -f $reqName, $entry.Line, $entry.Spec, $rc) 'err'
                    break
                }
            }

            if ($failedRequirements.Count -gt 0) {
                throw ("Falha ao instalar dependência do backend: {0}. Veja o log acima para o pacote exato e a mensagem do pip." -f ($failedRequirements -join '; '))
            }
            Log "[OK] Dependências do backend instaladas"

            P 77 'Validando dependências Python'
            Set-InstallState 'pip_check'
            $rc = Run $VENV_PY @('-m','pip','check') 'pip check'
            if ($rc -eq 0) { Log "[OK] pip check sem conflitos" } else { Log "[!] pip check encontrou conflitos; verifique o log acima se algo falhar ao iniciar" 'warn' }

            # ---- 9. onnxruntime-gpu (substituir CPU)
            if ($cfg.useOnnxGpu) {
                P 78 'Instalando onnxruntime-gpu'
                Set-InstallState 'installing_onnxruntime_gpu'
                [void](Run $VENV_PY @('-m','pip','uninstall','onnxruntime','-y') 'remover onnxruntime CPU')
                $rc = Run $VENV_PY ($pipInstall + @('onnxruntime-gpu')) 'onnxruntime-gpu'
                if ($rc -eq 0) { Log "[OK] onnxruntime-gpu instalado" } else {
                    Log "[!] onnxruntime-gpu falhou, voltando para CPU" 'warn'
                    [void](Run $VENV_PY ($pipInstall + @('onnxruntime')) 'onnxruntime CPU fallback')
                }
            }

            # ---- 10. npm install
            Set-InstallState 'installing_frontend'
            P 84 'Instalando pacotes npm'
            Set-Location -LiteralPath $ROOT
            if ([string]::IsNullOrWhiteSpace($NPM_EXE) -or -not (Test-Path -LiteralPath $NPM_EXE)) {
                throw "npm não encontrado. Instale Node.js 18+ pelo nodejs.org e abra o instalador novamente."
            }
            $rc = Run $NPM_EXE @('install','--no-audit','--no-fund') 'npm install'
            if ($rc -ne 0) { throw "Falha em npm install (exit $rc)" }
            Log "[OK] Pacotes npm instalados"

            # ---- 11. npm run build
            P 92 'Compilando frontend (~2-5 min)'
            $rc = Run $NPM_EXE @('run','build') 'npm run build'
            if ($rc -ne 0) { throw "Falha no build do frontend (exit $rc)" }
            Log "[OK] Frontend compilado"

            # ---- 12. Deploy frontend para backend\neveai\frontend
            P 97 'Implantando frontend no backend'
            $frontDir = Join-Path $BACKEND 'neveai\frontend'
            if (Test-Path $frontDir) { Remove-Item $frontDir -Recurse -Force }
            New-Item $frontDir -ItemType Directory -Force | Out-Null
            Copy-Item (Join-Path $ROOT 'build\*') $frontDir -Recurse -Force
            Log "[OK] Frontend copiado para backend\neveai\frontend"

            # ---- Done
            Set-InstallState 'done'
            P 100 'Concluído'

            # Resumo
            $summary = @()
            $summary += "Python:      $((& $PYTHON_EXE --version 2>&1))"
            $summary += "Node.js:     $((& $NODE_EXE --version 2>&1))"
            try {
                $tOut = & $VENV_PY -c "import torch; v=torch.__version__; cuda='(CUDA '+torch.version.cuda+')' if torch.cuda.is_available() else '(CPU)'; print('PyTorch '+v+' '+cuda)" 2>$null
                if ($tOut) { $summary += "PyTorch:     $tOut" }
            } catch {}
            $summary += "llama.cpp:   $($cfg.llamaAsset)"
            if ($vramGb -gt 0) { $summary += "VRAM:        ${vramGb} GB ($($detected.Name))" }

            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.InstallPanel.Visibility = 'Collapsed'
                $script:Ctl.DonePanel.Visibility    = 'Visible'
                $script:Ctl.LblSummary.Text         = ($summary -join "`r`n")
                $script:Ctl.BtnCancel.Visibility    = 'Collapsed'
                $script:Ctl.BtnPrimary.IsEnabled    = $true
                $script:Ctl.BtnPrimary.Content      = 'Concluir'
                $script:Ctl.BtnPrimary.Tag          = 'done'
                $script:Ctl.BtnClose.IsEnabled      = $true
                $script:Window.Tag = 'done'
            })
        } catch {
            $errMsg = "$($_.Exception.Message)"
            if (-not $errMsg) { $errMsg = "$_" }
            Set-InstallState 'failed'
            Log "[X] FALHA: $errMsg" 'err'
            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.LblStep.Text = "Falha durante a instalação."
                $script:Ctl.LblPhase.Text = "Falha durante a instalação."
                $script:Ctl.BtnPrimary.IsEnabled = $true
                $script:Ctl.BtnPrimary.Content   = 'Fechar'
                $script:Ctl.BtnPrimary.Tag       = 'done'
                $script:Ctl.BtnCancel.IsEnabled  = $true
                $script:Ctl.BtnClose.IsEnabled   = $true
                $script:Window.Tag = 'failed'
                [System.Windows.MessageBox]::Show("A instalação falhou. A janela ficará aberta para você ler o log.`n`nVeja logs\install.log`n`n$errMsg", 'Neve AI', 'OK', 'Error') | Out-Null
            })
        }
    }

    # Cria runspace e injeta o que precisamos
    $runspace = [RunspaceFactory]::CreateRunspace()
    $runspace.ApartmentState = 'STA'
    $runspace.ThreadOptions  = 'ReuseThread'
    $runspace.Open()
    $runspace.SessionStateProxy.SetVariable('Window', $window)
    $runspace.SessionStateProxy.SetVariable('Ctl',    $ctl)

    $ps = [PowerShell]::Create()
    $ps.Runspace = $runspace
    [void]$ps.AddScript($worker).AddArgument($cfg).AddArgument($flashAttn).AddArgument($vramGb).AddArgument($detected).AddArgument($ROOT).AddArgument($VENV_DIR).AddArgument($VENV_PY).AddArgument($BACKEND).AddArgument($LOG).AddArgument($STATE_FILE).AddArgument($PYTHON_EXE).AddArgument($NODE_EXE).AddArgument($NPM_EXE)
    [void]$ps.add_InvocationStateChanged({
        param($sender, $eventArgs)
        if ($eventArgs.InvocationStateInfo.State -eq 'Failed') {
            $fatal = $eventArgs.InvocationStateInfo.Reason
            $msg = if ($fatal) { $fatal.Message } else { 'Falha fatal no processo de instalação.' }
            try { [System.IO.File]::WriteAllText($STATE_FILE, 'failed', [System.Text.UTF8Encoding]::new($false)) } catch {}
            try { Add-Content -LiteralPath $LOG -Value "[FATAL] $msg" -Encoding UTF8 } catch {}
            try {
                $window.Dispatcher.Invoke([Action]{
                    $ctl.LblStep.Text = 'Falha fatal durante a instalação.'
                    $ctl.LblPhase.Text = 'Falha fatal durante a instalação.'
                    $ctl.BtnPrimary.IsEnabled = $true
                    $ctl.BtnPrimary.Content = 'Fechar'
                    $ctl.BtnPrimary.Tag = 'done'
                    $ctl.BtnCancel.IsEnabled = $true
                    $ctl.BtnClose.IsEnabled = $true
                    $window.Tag = 'failed'
                    $ctl.LogBox.AppendText("[FATAL] $msg`r`n")
                    $ctl.LogScroll.ScrollToEnd()
                })
            } catch {}
        }
    })
    $script:InstallerPowerShell = $ps
    $script:InstallerRunspace = $runspace
    $script:InstallerAsyncResult = $ps.BeginInvoke()
})

# =============================================================================
# Mostrar a janela
# =============================================================================
[void]$window.ShowDialog()
