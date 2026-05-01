# Neve AI - Instalador Grafico (WPF)
# UI bonita + progresso visual + log em tempo real.
# Toda a logica original (deteccao de GPU, llama.cpp, venv, requirements, npm)
# roda em runspace separado para nao travar a interface.

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding           = [Console]::OutputEncoding

Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase
Add-Type -AssemblyName System.Windows.Forms

# =============================================================================
# Caminhos globais
# =============================================================================
$ROOT     = Split-Path $MyInvocation.MyCommand.Path -Parent
$VENV_DIR = Join-Path $ROOT 'backend\neveai\venv'
$VENV_PY  = Join-Path $VENV_DIR 'Scripts\python.exe'
$BACKEND  = Join-Path $ROOT 'backend'
$LOG_DIR  = Join-Path $ROOT 'logs'
if (-not (Test-Path $LOG_DIR)) { New-Item $LOG_DIR -ItemType Directory | Out-Null }
$LOG = Join-Path $LOG_DIR 'install.log'
'' | Set-Content $LOG

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
                        <TextBlock Text="Bem-vindo ao Neve AI" FontSize="22" FontWeight="SemiBold" Foreground="#111111"/>
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

                            <TextBlock Grid.Row="3" Grid.Column="0" Text="Flash Attention:" FontSize="13" Foreground="#52525B" Margin="0,0,0,12"/>
                            <CheckBox  Grid.Row="3" Grid.Column="1" x:Name="ChkFlash" Content="Compilar Flash Attention (acelera RAG/SD, +10 min)" FontSize="13" Margin="0,2,0,12"/>

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

# Atalhos para controles
$ctl = @{}
foreach ($name in 'LogoImg','BtnClose','LblGpu','CmbBackend','CmbVram','ChkFlash',
                  'ConfigPanel','InstallPanel','DonePanel',
                  'LblStep','LblPhase','LblProgressTxt','Progress','LogBox','LogScroll',
                  'LblDoneTitle','LblDoneSub','LblSummary',
                  'BtnCancel','BtnPrimary') {
    $ctl[$name] = $window.FindName($name)
}

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

# Pre-checar Python e Node
$pyOk = $false; $pyVer = ''
try { $pyVer = (python --version 2>&1).ToString().Trim(); $pyOk = $LASTEXITCODE -eq 0 } catch {}
$nodeOk = $false; $nodeVer = ''
try { $nodeVer = (node --version 2>&1).ToString().Trim(); $nodeOk = $LASTEXITCODE -eq 0 } catch {}

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
    if (-not $pyOk)   { $missing += 'Python 3.11/3.12 (https://python.org)' }
    if (-not $nodeOk) { $missing += 'Node.js 18+ (https://nodejs.org)' }
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

function Run-Logged([string]$exe, [string[]]$args, [string]$desc) {
    UI-Log $desc 'info'
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName               = $exe
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true
    $psi.UseShellExecute        = $false
    $psi.CreateNoWindow         = $true
    foreach ($a in $args) { $psi.ArgumentList.Add($a) }
    $proc = [System.Diagnostics.Process]::Start($psi)
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()
    if ($stdout) { Add-Content $LOG $stdout }
    if ($stderr) { Add-Content $LOG $stderr }
    return $proc.ExitCode
}

# =============================================================================
# Worker - executa em runspace separado
# =============================================================================
$ctl.BtnPrimary.Add_Click({
    if ($ctl.BtnPrimary.Tag -eq 'done') { $window.Close(); return }

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
        8 { @{ torchIndex='https://download.pytorch.org/whl/rocm6.3'; llamaAsset='hip-radeon'; cudaVer='ROCm 6.3';            useOnnxGpu=$false; vendor='AMD'    } }
        9 { @{ torchIndex='https://download.pytorch.org/whl/cpu'; llamaAsset='vulkan';         cudaVer='Vulkan';              useOnnxGpu=$false; vendor='AMD'    } }
        default { @{ torchIndex='https://download.pytorch.org/whl/cpu'; llamaAsset='cpu'; cudaVer='CPU'; useOnnxGpu=$false; vendor='CPU' } }
    }

    # Trocar para a tela de instalacao
    $ctl.ConfigPanel.Visibility = 'Collapsed'
    $ctl.InstallPanel.Visibility = 'Visible'
    $ctl.BtnPrimary.IsEnabled = $false
    $ctl.BtnCancel.IsEnabled  = $false

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
        $summary += "Python:      $((python --version 2>&1))"
        $summary += "Node.js:     $((node --version 2>&1))"
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
        return
    }

    # Worker em runspace separado, usando as funcoes UI-* via $window
    $worker = {
        param($cfg, $flashAttn, $vramGb, $detected, $ROOT, $VENV_DIR, $VENV_PY, $BACKEND, $LOG)

        # Helpers (definidas dentro do runspace)
        function Log([string]$m, [string]$k='info') {
            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.LogBox.AppendText("$m`r`n")
                $script:Ctl.LogScroll.ScrollToEnd()
            })
            Add-Content $LOG $m
        }
        function P([int]$v, [string]$phase) {
            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.Progress.Value = $v
                $script:Ctl.LblProgressTxt.Text = "$v%"
                if ($phase) { $script:Ctl.LblPhase.Text = $phase; $script:Ctl.LblStep.Text = $phase }
            })
        }
        function Run([string]$exe, [string[]]$argv, [string]$desc) {
            Log "==> $desc"
            $psi = New-Object System.Diagnostics.ProcessStartInfo
            $psi.FileName = $exe
            $psi.RedirectStandardOutput = $true
            $psi.RedirectStandardError  = $true
            $psi.UseShellExecute = $false
            $psi.CreateNoWindow  = $true
            foreach ($a in $argv) { [void]$psi.ArgumentList.Add($a) }
            $p = [System.Diagnostics.Process]::Start($psi)
            $out = $p.StandardOutput.ReadToEnd()
            $err = $p.StandardError.ReadToEnd()
            $p.WaitForExit()
            if ($out) { Add-Content $LOG $out }
            if ($err) { Add-Content $LOG $err }
            return $p.ExitCode
        }

        try {
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
            if (-not (Test-Path $envPath)) {                @"
VITE_RELATIVE_CONFIG=True
VITE_OPENWEBUI_BACKEND_URL=http://localhost:8080
ENV=dev
PORT=8080
WEBUI_SECRET_KEY=troque-esta-chave-por-algo-seguro
WEBUI_AUTH=False
WEBUI_NAME=Neve AI
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
"@ | Set-Content $envPath
                Log "[OK] .env criado"
            } else {
                Log "[…] .env preservado"
            }

            # ---- 3. llama.cpp
            P 12 'Baixando llama.cpp'
            $llamaDir = Join-Path $ROOT 'llamacpp-server\bin'
            if (-not (Test-Path (Split-Path $llamaDir -Parent))) { New-Item (Split-Path $llamaDir -Parent) -ItemType Directory | Out-Null }
            if (-not (Test-Path $llamaDir)) { New-Item $llamaDir -ItemType Directory | Out-Null }
            try {
                $rel = Invoke-RestMethod 'https://api.github.com/repos/ggml-org/llama.cpp/releases/latest' -Headers @{ 'User-Agent' = 'Neve-Installer/3.0' }
                $tag = $rel.tag_name
                $binName = "llama-$tag-bin-win-$($cfg.llamaAsset)-x64.zip"
                $binObj  = $rel.assets | Where-Object { $_.name -eq $binName } | Select-Object -First 1
                if (-not $binObj) {
                    Log "[!] Asset $binName não encontrado, usando CPU como fallback" 'warn'
                    $binName = "llama-$tag-bin-win-cpu-x64.zip"
                    $binObj  = $rel.assets | Where-Object { $_.name -eq $binName } | Select-Object -First 1
                }
                if ($binObj) {
                    $sizeMB = [math]::Round($binObj.size/1MB,0)
                    Log "==> Baixando $binName ($sizeMB MB)"
                    $tmp = Join-Path $env:TEMP 'neve_llama_bin.zip'
                    Invoke-WebRequest $binObj.browser_download_url -OutFile $tmp -UseBasicParsing
                    Get-ChildItem $llamaDir -Filter '*.exe' -EA SilentlyContinue | Remove-Item -Force
                    Get-ChildItem $llamaDir -Filter '*.dll' -EA SilentlyContinue | Remove-Item -Force
                    $ext = Join-Path $env:TEMP 'neve_llama_ext'
                    if (Test-Path $ext) { Remove-Item $ext -Recurse -Force }
                    Expand-Archive $tmp -DestinationPath $ext -Force
                    Get-ChildItem $ext -Recurse -File | ForEach-Object { Copy-Item $_.FullName $llamaDir -Force }
                    Remove-Item $ext -Recurse -Force
                    Remove-Item $tmp -Force
                    Log "[OK] llama.cpp $tag instalado"
                }
                if ($cfg.llamaAsset -match '^cuda-') {
                    P 18 'Baixando CUDA Runtime'
                    $dllName = "cudart-llama-bin-win-$($cfg.llamaAsset)-x64.zip"
                    $dllObj  = $rel.assets | Where-Object { $_.name -eq $dllName } | Select-Object -First 1
                    if ($dllObj) {
                        $sizeMB = [math]::Round($dllObj.size/1MB,0)
                        Log "==> Baixando $dllName ($sizeMB MB)"
                        $tmp = Join-Path $env:TEMP 'neve_cudart.zip'
                        Invoke-WebRequest $dllObj.browser_download_url -OutFile $tmp -UseBasicParsing
                        $ext = Join-Path $env:TEMP 'neve_cudart_ext'
                        if (Test-Path $ext) { Remove-Item $ext -Recurse -Force }
                        Expand-Archive $tmp -DestinationPath $ext -Force
                        Get-ChildItem $ext -Recurse -File | ForEach-Object { Copy-Item $_.FullName $llamaDir -Force }
                        Remove-Item $ext -Recurse -Force
                        Remove-Item $tmp -Force
                        Log "[OK] CUDA Runtime DLLs instaladas"
                    }
                }
            } catch {
                Log "[!] Falha ao baixar llama.cpp: $_" 'warn'
            }

            # ---- 4. Recriar venv
            P 25 'Recriando ambiente Python'
            if (Test-Path $VENV_DIR) {
                Log "==> Removendo venv antigo"
                try { Remove-Item $VENV_DIR -Recurse -Force -EA Stop } catch {
                    Log "[X] Falha ao remover venv: $_" 'err'; throw
                }
            }
            $rc = Run 'python' @('-m','venv',$VENV_DIR) 'Criando venv'
            if ($rc -ne 0) { throw "Falha ao criar venv (exit $rc)" }
            Log "[OK] venv criado"

            # ---- 5. pip + PyTorch
            P 32 'Atualizando pip'
            [void](Run $VENV_PY @('-m','pip','install','--upgrade','pip') 'pip upgrade')

            P 38 "Instalando PyTorch ($($cfg.cudaVer))"
            $rc = Run $VENV_PY @('-m','pip','install','torch','torchvision','--index-url',$cfg.torchIndex) 'PyTorch + torchvision'
            if ($rc -ne 0) { throw "Falha ao instalar PyTorch (exit $rc)" }
            Log "[OK] PyTorch instalado"

            # ---- 6. Flash Attention (opcional)
            if ($flashAttn -and $cfg.vendor -eq 'NVIDIA') {
                P 48 'Compilando Flash Attention (~10 min)'
                $rc = Run $VENV_PY @('-m','pip','install','flash-attn','--no-build-isolation') 'flash-attn'
                if ($rc -eq 0) { Log "[OK] Flash Attention instalado" } else { Log "[!] Flash Attention falhou (precisa MSVC Build Tools)" 'warn' }
            }

            # ---- 7. diffusers
            P 55 'Instalando diffusers'
            [void](Run $VENV_PY @('-m','pip','install','diffusers') 'diffusers')

            # ---- 8. requirements do backend
            P 60 'Instalando dependências do backend (~5-15 min)'
            $req = Join-Path $BACKEND 'requirements.txt'
            $rc = Run $VENV_PY @('-m','pip','install','-r',$req) 'requirements.txt'
            if ($rc -ne 0) { Log "[!] Algumas dependências podem ter falhado" 'warn' } else { Log "[OK] Dependências do backend instaladas" }

            # ---- 9. onnxruntime-gpu (substituir CPU)
            if ($cfg.useOnnxGpu) {
                P 78 'Instalando onnxruntime-gpu'
                [void](Run $VENV_PY @('-m','pip','uninstall','onnxruntime','-y') 'remover onnxruntime CPU')
                $rc = Run $VENV_PY @('-m','pip','install','onnxruntime-gpu') 'onnxruntime-gpu'
                if ($rc -eq 0) { Log "[OK] onnxruntime-gpu instalado" } else {
                    Log "[!] onnxruntime-gpu falhou, voltando para CPU" 'warn'
                    [void](Run $VENV_PY @('-m','pip','install','onnxruntime') 'onnxruntime CPU fallback')
                }
            }

            # ---- 10. npm install
            P 84 'Instalando pacotes npm'
            Set-Location $ROOT
            $rc = Run 'npm.cmd' @('install') 'npm install'
            if ($rc -ne 0) { throw "Falha em npm install (exit $rc)" }
            Log "[OK] Pacotes npm instalados"

            # ---- 11. npm run build
            P 92 'Compilando frontend (~2-5 min)'
            $rc = Run 'npm.cmd' @('run','build') 'npm run build'
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
            P 100 'Concluído'

            # Resumo
            $summary = @()
            $summary += "Python:      $((python --version 2>&1))"
            $summary += "Node.js:     $((node --version 2>&1))"
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
            })
        } catch {
            Log "[X] FALHA: $_" 'err'
            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.LblStep.Text = "Falha durante a instalação."
                $script:Ctl.BtnPrimary.IsEnabled = $true
                $script:Ctl.BtnPrimary.Content   = 'Fechar'
                $script:Ctl.BtnPrimary.Tag       = 'done'
                $script:Ctl.BtnCancel.IsEnabled  = $true
                [System.Windows.MessageBox]::Show("A instalação falhou. Veja o log em logs\install.log`n`n$_", 'Neve AI', 'OK', 'Error') | Out-Null
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
    [void]$ps.AddScript($worker).AddArgument($cfg).AddArgument($flashAttn).AddArgument($vramGb).AddArgument($detected).AddArgument($ROOT).AddArgument($VENV_DIR).AddArgument($VENV_PY).AddArgument($BACKEND).AddArgument($LOG)
    [void]$ps.BeginInvoke()
})

# =============================================================================
# Mostrar a janela
# =============================================================================
[void]$window.ShowDialog()
