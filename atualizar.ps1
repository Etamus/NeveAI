# Neve AI - Atualizador Grafico (WPF)
# Verifica a ultima release em github.com/Etamus/NeveAI, baixa, aplica e refaz o build.

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding           = [Console]::OutputEncoding

Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase
Add-Type -AssemblyName System.Windows.Forms

# =============================================================================
# Caminhos globais
# =============================================================================
$ROOT        = Split-Path $MyInvocation.MyCommand.Path -Parent
$VENV_PY     = Join-Path $ROOT 'backend\neveai\venv\Scripts\python.exe'
$VERSION_FILE= Join-Path $ROOT 'version.txt'
$LOG_DIR     = Join-Path $ROOT 'logs'
if (-not (Test-Path $LOG_DIR)) { New-Item $LOG_DIR -ItemType Directory | Out-Null }
$LOG = Join-Path $LOG_DIR 'update.log'
'' | Set-Content $LOG

$REPO_OWNER  = 'Etamus'
$REPO_NAME   = 'NeveAI'
$API_LATEST  = "https://api.github.com/repos/$REPO_OWNER/$REPO_NAME/releases/latest"
$LLAMA_API_LATEST = 'https://api.github.com/repos/ggml-org/llama.cpp/releases/latest'
$UA          = 'Neve-Updater/1.0'

# Logo (favicon do projeto)
$LOGO_PATH = Join-Path $ROOT 'static\favicon.png'
if (-not (Test-Path $LOGO_PATH)) { $LOGO_PATH = Join-Path $ROOT 'static\static\favicon.png' }

# =============================================================================
# XAML - Interface
# =============================================================================
[xml]$xaml = @"
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Neve AI - Atualizador"
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
        <Style x:Key="AccentBtn" TargetType="Button" BasedOn="{StaticResource PrimaryBtn}">
            <Setter Property="Background" Value="#2563EB"/>
            <Setter Property="Foreground" Value="White"/>
            <Setter Property="Padding" Value="18,9"/>
            <Setter Property="MinWidth" Value="154"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="Button">
                        <Border x:Name="bd" Background="{TemplateBinding Background}" CornerRadius="8" Padding="{TemplateBinding Padding}">
                            <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
                        </Border>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="bd" Property="Background" Value="#1D4ED8"/>
                            </Trigger>
                            <Trigger Property="IsEnabled" Value="False">
                                <Setter TargetName="bd" Property="Opacity" Value="0.45"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
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
                    <TextBlock Text="  ·  Atualizador" FontSize="13" Foreground="#71717A" VerticalAlignment="Center"/>
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

            <!-- BODY -->
            <Grid Grid.Row="1" Margin="32,8,32,0">

                <!-- CHECK PANEL -->
                <Grid x:Name="CheckPanel">
                    <Grid.RowDefinitions>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="*"/>
                    </Grid.RowDefinitions>

                    <StackPanel Grid.Row="0" Margin="0,0,0,18">
                        <TextBlock x:Name="LblCheckTitle" Text="Verificando atualizações…" FontSize="22" FontWeight="SemiBold" Foreground="#111111"/>
                        <TextBlock x:Name="LblCheckSub" Text="Consultando GitHub…" FontSize="13" Foreground="#71717A" Margin="0,4,0,0"/>
                    </StackPanel>

                    <Border Grid.Row="1" Background="White" CornerRadius="10" BorderBrush="#E4E4E7" BorderThickness="1" Padding="20">
                        <Grid>
                            <Grid.RowDefinitions>
                                <RowDefinition Height="Auto"/>
                                <RowDefinition Height="Auto"/>
                                <RowDefinition Height="*"/>
                            </Grid.RowDefinitions>

                            <Grid Grid.Row="0" Margin="0,0,0,16">
                                <Grid.ColumnDefinitions>
                                    <ColumnDefinition Width="0.92*"/>
                                    <ColumnDefinition Width="1"/>
                                    <ColumnDefinition Width="1.08*"/>
                                </Grid.ColumnDefinitions>

                                <Grid Grid.Column="0" Margin="0,0,14,0">
                                    <Grid.RowDefinitions>
                                        <RowDefinition Height="Auto"/>
                                        <RowDefinition Height="Auto"/>
                                        <RowDefinition Height="Auto"/>
                                        <RowDefinition Height="Auto"/>
                                    </Grid.RowDefinitions>
                                    <Grid.ColumnDefinitions>
                                        <ColumnDefinition Width="118"/>
                                        <ColumnDefinition Width="*"/>
                                    </Grid.ColumnDefinitions>

                                    <Grid Grid.Row="0" Grid.ColumnSpan="2" Margin="0,0,0,8">
                                        <TextBlock Text="Neve AI" FontSize="13" FontWeight="SemiBold" Foreground="#111111"/>
                                        <CheckBox x:Name="ChkUpdateNeve" HorizontalAlignment="Right" VerticalAlignment="Center" Visibility="Collapsed"/>
                                    </Grid>

                                    <TextBlock Grid.Row="1" Grid.Column="0" Text="Versão instalada:" FontSize="13" Foreground="#52525B" Margin="0,0,0,10"/>
                                    <TextBlock Grid.Row="1" Grid.Column="1" x:Name="LblCurrent" Text="—" FontSize="13" FontWeight="SemiBold" Foreground="#111111" Margin="0,0,0,10" TextTrimming="CharacterEllipsis"/>

                                    <TextBlock Grid.Row="2" Grid.Column="0" Text="Última disponível:" FontSize="13" Foreground="#52525B" Margin="0,0,0,10"/>
                                    <TextBlock Grid.Row="2" Grid.Column="1" x:Name="LblLatest" Text="—" FontSize="13" FontWeight="SemiBold" Foreground="#111111" Margin="0,0,0,10" TextTrimming="CharacterEllipsis"/>

                                    <TextBlock Grid.Row="3" Grid.Column="0" Text="Status:" FontSize="13" Foreground="#52525B" Margin="0,0,0,0"/>
                                    <TextBlock Grid.Row="3" Grid.Column="1" x:Name="LblStatus" Text="Aguardando…" FontSize="13" FontWeight="SemiBold" Foreground="#71717A" TextTrimming="CharacterEllipsis"/>
                                </Grid>

                                <Border Grid.Column="1" BorderBrush="#E4E4E7" BorderThickness="1,0,0,0"/>

                                <Grid Grid.Column="2" Margin="12,0,0,0">
                                    <Grid.RowDefinitions>
                                        <RowDefinition Height="Auto"/>
                                        <RowDefinition Height="Auto"/>
                                        <RowDefinition Height="Auto"/>
                                        <RowDefinition Height="Auto"/>
                                    </Grid.RowDefinitions>
                                    <Grid.ColumnDefinitions>
                                        <ColumnDefinition Width="118"/>
                                        <ColumnDefinition Width="*"/>
                                    </Grid.ColumnDefinitions>

                                    <Grid Grid.Row="0" Grid.ColumnSpan="2" Margin="0,0,0,8">
                                        <TextBlock Text="llama.cpp" FontSize="13" FontWeight="SemiBold" Foreground="#111111"/>
                                        <CheckBox x:Name="ChkUpdateLlama" HorizontalAlignment="Right" VerticalAlignment="Center" Visibility="Collapsed"/>
                                    </Grid>

                                    <TextBlock Grid.Row="1" Grid.Column="0" Text="Versão instalada:" FontSize="13" Foreground="#52525B" Margin="0,0,0,10"/>
                                    <TextBlock Grid.Row="1" Grid.Column="1" x:Name="LblLlamaCurrent" Text="—" FontSize="13" FontWeight="SemiBold" Foreground="#111111" Margin="0,0,0,10" TextTrimming="CharacterEllipsis"/>

                                    <TextBlock Grid.Row="2" Grid.Column="0" Text="Última disponível:" FontSize="13" Foreground="#52525B" Margin="0,0,0,10"/>
                                    <TextBlock Grid.Row="2" Grid.Column="1" x:Name="LblLlamaLatest" Text="—" FontSize="13" FontWeight="SemiBold" Foreground="#111111" Margin="0,0,0,10" TextTrimming="CharacterEllipsis"/>

                                    <TextBlock Grid.Row="3" Grid.Column="0" Text="Status:" FontSize="13" Foreground="#52525B" Margin="0,0,0,0"/>
                                    <TextBlock Grid.Row="3" Grid.Column="1" x:Name="LblLlamaStatus" Text="Aguardando…" FontSize="13" FontWeight="SemiBold" Foreground="#71717A" TextTrimming="CharacterEllipsis"/>
                                </Grid>
                            </Grid>

                            <TextBlock Grid.Row="1" Text="Notas da release do Neve AI:" FontSize="13" FontWeight="SemiBold" Foreground="#111111" Margin="0,0,0,6"/>

                            <Border Grid.Row="2" Background="#FAFAFA" CornerRadius="8" Padding="12,10">
                                <ScrollViewer VerticalScrollBarVisibility="Auto">
                                    <TextBox x:Name="LblNotes" Text="" Background="Transparent" BorderThickness="0"
                                             IsReadOnly="True" FontFamily="Consolas" FontSize="11" Foreground="#52525B"
                                             TextWrapping="Wrap" AcceptsReturn="True"/>
                                </ScrollViewer>
                            </Border>
                        </Grid>
                    </Border>
                </Grid>

                <!-- UPDATE PANEL -->
                <Grid x:Name="UpdatePanel" Visibility="Collapsed">
                    <Grid.RowDefinitions>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="*"/>
                    </Grid.RowDefinitions>

                    <StackPanel Grid.Row="0" Margin="0,0,0,12">
                        <TextBlock Text="Atualizando…" FontSize="22" FontWeight="SemiBold" Foreground="#111111"/>
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

                <!-- DONE PANEL -->
                <Grid x:Name="DonePanel" Visibility="Collapsed">
                    <Border Background="White" CornerRadius="10" BorderBrush="#E4E4E7" BorderThickness="1" Padding="32">
                        <StackPanel HorizontalAlignment="Center" VerticalAlignment="Center">
                            <Border Width="56" Height="56" CornerRadius="28" Background="#10B981" Margin="0,0,0,18">
                                <TextBlock Text="OK" FontSize="20" FontWeight="Bold" Foreground="White" HorizontalAlignment="Center" VerticalAlignment="Center"/>
                            </Border>
                            <TextBlock x:Name="LblDoneTitle" Text="Atualização concluída!" FontSize="22" FontWeight="SemiBold" Foreground="#111111" HorizontalAlignment="Center"/>
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
                    <Button x:Name="BtnLlama" Style="{StaticResource AccentBtn}" Content="Atualizar llama.cpp" Margin="0,0,10,0" ToolTip="Atualização opcional, separada do Neve AI" Visibility="Collapsed"/>
                    <Button x:Name="BtnCancel" Style="{StaticResource GhostBtn}" Content="Cancelar" Margin="0,0,10,0"/>
                    <Button x:Name="BtnPrimary" Style="{StaticResource PrimaryBtn}" Content="Atualizar" IsEnabled="False" Visibility="Collapsed"/>
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

$ctl = @{}
foreach ($name in 'LogoImg','BtnClose',
                  'CheckPanel','UpdatePanel','DonePanel',
                  'LblCheckTitle','LblCheckSub','LblCurrent','LblLatest','LblStatus','LblNotes',
                  'LblLlamaCurrent','LblLlamaLatest','LblLlamaStatus',
                  'ChkUpdateNeve','ChkUpdateLlama',
                  'LblStep','LblPhase','LblProgressTxt','Progress','LogBox','LogScroll',
                  'LblDoneTitle','LblDoneSub','LblSummary',
                  'BtnLlama','BtnCancel','BtnPrimary') {
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

$window.Add_MouseLeftButtonDown({
    param($s, $e)
    if ($e.ButtonState -eq 'Pressed') { try { $window.DragMove() } catch {} }
})

$ctl.BtnClose.Add_Click({ $window.Close() })
$ctl.BtnCancel.Add_Click({ $window.Close() })

# =============================================================================
# Helpers de UI (chamáveis fora da thread principal via Dispatcher)
# =============================================================================
function Set-UI([scriptblock]$sb) { $window.Dispatcher.Invoke([Action]$sb) }

function Append-Log([string]$msg, [string]$kind = 'info') {
    $ts = (Get-Date).ToString('HH:mm:ss')
    $line = "[$ts] $msg"
    Add-Content -Path $LOG -Value $line -Encoding UTF8
    Set-UI {
        $ctl.LogBox.AppendText($line + "`r`n")
        $ctl.LogScroll.ScrollToEnd()
    }
}

function Set-Progress([int]$pct, [string]$phase) {
    Set-UI {
        $ctl.Progress.Value = $pct
        $ctl.LblProgressTxt.Text = "$pct%"
        if ($phase) { $ctl.LblPhase.Text = $phase; $ctl.LblStep.Text = $phase }
    }
}

function Update-PrimaryButtonState {
    $hasSelection = [bool]$ctl.ChkUpdateNeve.IsChecked -or [bool]$ctl.ChkUpdateLlama.IsChecked
    if ($hasSelection) {
        $ctl.BtnPrimary.Content = 'Atualizar'
        $ctl.BtnPrimary.Tag = 'update'
        $ctl.BtnPrimary.IsEnabled = $true
        $ctl.BtnPrimary.Visibility = 'Visible'
    } else {
        $ctl.BtnPrimary.IsEnabled = $false
        $ctl.BtnPrimary.Visibility = 'Collapsed'
    }
}

$ctl.ChkUpdateNeve.Add_Checked({ Update-PrimaryButtonState })
$ctl.ChkUpdateNeve.Add_Unchecked({ Update-PrimaryButtonState })
$ctl.ChkUpdateLlama.Add_Checked({ Update-PrimaryButtonState })
$ctl.ChkUpdateLlama.Add_Unchecked({ Update-PrimaryButtonState })

# =============================================================================
# Worker separado: atualizacao opcional do llama.cpp
# =============================================================================
$ctl.BtnLlama.Add_Click({
    $ctl.CheckPanel.Visibility  = 'Collapsed'
    $ctl.DonePanel.Visibility   = 'Collapsed'
    $ctl.UpdatePanel.Visibility = 'Visible'
    $ctl.LogBox.Clear()
    $ctl.Progress.Value = 0
    $ctl.LblProgressTxt.Text = '0%'
    $ctl.LblPhase.Text = 'Preparando'
    $ctl.LblStep.Text = 'Preparando atualização do llama.cpp...'
    $ctl.BtnPrimary.IsEnabled = $false
    $ctl.BtnLlama.IsEnabled   = $false
    $ctl.BtnCancel.IsEnabled  = $false

    $argRoot      = $ROOT
    $argLog       = $LOG
    $argLlamaApi  = $LLAMA_API_LATEST
    $argUa        = $UA

    $worker = {
        param($ROOT, $LOG, $LLAMA_API_LATEST, $UA)

        function L([string]$m, [string]$k='info') {
            $ts = (Get-Date).ToString('HH:mm:ss')
            $line = "[$ts] $m"
            Add-Content -Path $LOG -Value $line -Encoding UTF8
            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.LogBox.AppendText($line + "`r`n")
                $script:Ctl.LogScroll.ScrollToEnd()
            })
        }
        function P([int]$v, [string]$phase) {
            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.Progress.Value = $v
                $script:Ctl.LblProgressTxt.Text = "$v%"
                if ($phase) { $script:Ctl.LblPhase.Text = $phase; $script:Ctl.LblStep.Text = $phase }
            })
        }
        function New-LlamaTarget([string]$vendor, [string]$name, [string]$label, [string[]]$backends, [string]$reason) {
            [pscustomobject]@{
                Vendor   = $vendor
                Name     = $name
                Label    = $label
                Backends = $backends
                Reason   = $reason
            }
        }
        function Convert-ToInvariantDouble([string]$value) {
            if ([string]::IsNullOrWhiteSpace($value)) { return $null }
            try {
                return [double]::Parse(($value.Trim() -replace ',', '.'), [System.Globalization.CultureInfo]::InvariantCulture)
            } catch {
                return $null
            }
        }
        function Get-LlamaHardwareTarget {
            $nvidiaLine = $null
            try {
                $nvidiaOut = nvidia-smi --query-gpu=name,compute_cap --format=csv,noheader 2>&1
                if ($LASTEXITCODE -eq 0 -and "$nvidiaOut" -notmatch 'failed|not found|invalid') {
                    $nvidiaLine = ("$nvidiaOut" -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -First 1)
                }
            } catch {}

            if (-not $nvidiaLine) {
                try {
                    $nvidiaOut = nvidia-smi --query-gpu=name --format=csv,noheader 2>&1
                    if ($LASTEXITCODE -eq 0 -and "$nvidiaOut" -notmatch 'failed|not found|invalid') {
                        $nameOnly = ("$nvidiaOut" -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -First 1).Trim()
                        if ($nameOnly) { $nvidiaLine = $nameOnly }
                    }
                } catch {}
            }

            if ($nvidiaLine) {
                $parts = $nvidiaLine -split ','
                $name = $parts[0].Trim()
                $computeCap = $null
                if ($parts.Count -gt 1) { $computeCap = Convert-ToInvariantDouble $parts[1] }

                if ($computeCap -ne $null -and $computeCap -lt 5.0) {
                    return New-LlamaTarget 'CPU' $name 'CPU (GPU NVIDIA sem suporte CUDA moderno)' @('cpu') "GPU NVIDIA detectada ($name), mas compute capability $computeCap não é suportada pelos binários CUDA atuais."
                }

                if ($name -match 'RTX\s*5\d{3}|50\d{2}|Blackwell' -or ($computeCap -ne $null -and $computeCap -ge 12.0)) {
                    return New-LlamaTarget 'NVIDIA' $name 'NVIDIA CUDA 13.1' @('cuda-13.1','cuda-cu13.1') "GPU NVIDIA Blackwell detectada: $name."
                }

                if ($computeCap -ne $null -and $computeCap -ge 5.0) {
                    return New-LlamaTarget 'NVIDIA' $name 'NVIDIA CUDA 12.4' @('cuda-12.4','cuda-cu12.4') "GPU NVIDIA compatível com CUDA 12 detectada: $name."
                }

                if ($name -match 'RTX\s*[234]\d{3}|[234]0\d{2}|GTX\s*16\d{2}|GTX\s*10\d{2}|GTX\s*9\d{2}|Quadro|Tesla|RTX\s*A') {
                    return New-LlamaTarget 'NVIDIA' $name 'NVIDIA CUDA 12.4' @('cuda-12.4','cuda-cu12.4') "GPU NVIDIA reconhecida por geração: $name."
                }

                throw "GPU NVIDIA detectada ($name), mas não foi possível determinar com segurança o binário CUDA correto. Nada foi instalado."
            }

            try {
                $gpus = Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name -EA SilentlyContinue
                $amdGpu = $gpus | Where-Object { $_ -match 'AMD|Radeon|RX\s' } | Select-Object -First 1
                if ($amdGpu) {
                    return New-LlamaTarget 'AMD' $amdGpu.Trim() 'AMD Vulkan' @('vulkan') "GPU AMD detectada: $($amdGpu.Trim())."
                }
            } catch {}

            return New-LlamaTarget 'CPU' '' 'CPU' @('cpu') 'Nenhuma GPU NVIDIA/AMD compatível foi detectada.'
        }
        function Find-LlamaBinAsset($assets, [string]$tag, [string[]]$backends) {
            $tagEsc = [regex]::Escape($tag)
            foreach ($backend in $backends) {
                $backendEsc = [regex]::Escape($backend)
                $match = $assets | Where-Object { $_.name -match "^llama-$tagEsc-bin-win-$backendEsc-x64\.zip$" } | Select-Object -First 1
                if ($match) { return $match }
            }
            foreach ($backend in $backends) {
                $backendEsc = [regex]::Escape($backend)
                $match = $assets | Where-Object { $_.name -match "^llama-.+-bin-win-$backendEsc-x64\.zip$" } | Select-Object -First 1
                if ($match) { return $match }
            }
            return $null
        }
        function Find-CudaRuntimeAsset($assets, [string[]]$backends) {
            foreach ($backend in $backends) {
                $backendEsc = [regex]::Escape($backend)
                $match = $assets | Where-Object { $_.name -match "^cudart-llama-bin-win-$backendEsc-x64\.zip$" } | Select-Object -First 1
                if ($match) { return $match }
            }
            return $null
        }
        function Get-InstalledLlamaInfo([string]$root) {
            $versionPath = Join-Path $root 'llamacpp-server\version.txt'
            $tag = ''
            $backend = ''
            $asset = ''
            if (Test-Path $versionPath) {
                $lines = @(Get-Content $versionPath -EA SilentlyContinue)
                if ($lines.Count -gt 0) { $tag = $lines[0].Trim() }
                if ($lines.Count -gt 1) { $backend = $lines[1].Trim() }
                if ($lines.Count -gt 2) { $asset = $lines[2].Trim() }
            }
            [pscustomobject]@{
                Tag = $tag
                Backend = $backend
                Asset = $asset
            }
        }

        $tmpFiles = @()
        $stageDir = $null
        $backupDir = $null
        try {
            P 5 'Consultando release do llama.cpp'
            $rel = Invoke-RestMethod $LLAMA_API_LATEST -Headers @{ 'User-Agent' = $UA } -TimeoutSec 30
            $tag = $rel.tag_name
            if (-not $tag) { throw 'Release do llama.cpp sem tag_name.' }
            L "[OK] Último release: $tag"

            $installed = Get-InstalledLlamaInfo $ROOT
            if ($installed.Tag -and $installed.Tag -eq $tag) {
                P 100 'llama.cpp atualizado'
                L "[OK] llama.cpp já está na última release ($tag). Nenhum download necessário."

                $summary = "Release instalada: $($installed.Tag)`r`nÚltima disponível: $tag`r`nStatus: atualizado"
                if ($installed.Backend) { $summary += "`r`nBackend: $($installed.Backend)" }
                if ($installed.Asset) { $summary += "`r`nAsset:   $($installed.Asset)" }

                $script:Window.Dispatcher.Invoke([Action]{
                    $script:Ctl.UpdatePanel.Visibility = 'Collapsed'
                    $script:Ctl.DonePanel.Visibility   = 'Visible'
                    $script:Ctl.LblDoneTitle.Text = 'llama.cpp já está atualizado'
                    $script:Ctl.LblDoneSub.Text   = 'A versão instalada já é a última release disponível.'
                    $script:Ctl.LblSummary.Text   = $summary
                    $script:Ctl.BtnPrimary.Content   = 'Concluir'
                    $script:Ctl.BtnPrimary.Tag       = 'done'
                    $script:Ctl.BtnPrimary.IsEnabled = $true
                    $script:Ctl.BtnLlama.IsEnabled   = $false
                    $script:Ctl.BtnCancel.IsEnabled  = $false
                })
                return
            }

            P 15 'Detectando hardware'
            $target = Get-LlamaHardwareTarget
            L "[OK] Alvo selecionado: $($target.Label)"
            if ($target.Name) { L "    Hardware: $($target.Name)" }
            if ($target.Reason) { L "    $($target.Reason)" }

            $mainAsset = Find-LlamaBinAsset $rel.assets $tag ([string[]]$target.Backends)
            if (-not $mainAsset) {
                throw "O release $tag não contém um asset Windows x64 para $($target.Label). Nada foi instalado."
            }

            $isCuda = (@($target.Backends) | Where-Object { $_ -match '^cuda' } | Select-Object -First 1) -ne $null
            $runtimeAsset = $null
            if ($isCuda) { $runtimeAsset = Find-CudaRuntimeAsset $rel.assets ([string[]]$target.Backends) }

            P 28 'Baixando binários'
            $tmpMain = Join-Path $env:TEMP "neve_llama_$([guid]::NewGuid().ToString('N')).zip"
            $tmpFiles += $tmpMain
            $sizeMB = [math]::Round($mainAsset.size / 1MB, 1)
            L "==> Baixando $($mainAsset.name) ($sizeMB MB)"
            Invoke-WebRequest $mainAsset.browser_download_url -OutFile $tmpMain -UseBasicParsing -Headers @{ 'User-Agent' = $UA }

            $tmpRuntime = $null
            if ($runtimeAsset) {
                $tmpRuntime = Join-Path $env:TEMP "neve_llama_cudart_$([guid]::NewGuid().ToString('N')).zip"
                $tmpFiles += $tmpRuntime
                $runtimeMB = [math]::Round($runtimeAsset.size / 1MB, 1)
                L "==> Baixando $($runtimeAsset.name) ($runtimeMB MB)"
                Invoke-WebRequest $runtimeAsset.browser_download_url -OutFile $tmpRuntime -UseBasicParsing -Headers @{ 'User-Agent' = $UA }
            } elseif ($isCuda) {
                L '[!] Runtime CUDA separado não encontrado no release; prosseguindo apenas com o pacote principal.' 'warn'
            }

            P 45 'Extraindo e validando'
            $stageDir = Join-Path $env:TEMP "neve_llama_stage_$([guid]::NewGuid().ToString('N'))"
            New-Item $stageDir -ItemType Directory -Force | Out-Null
            Expand-Archive $tmpMain -DestinationPath $stageDir -Force
            if ($tmpRuntime) { Expand-Archive $tmpRuntime -DestinationPath $stageDir -Force }
            $serverExe = Get-ChildItem $stageDir -Recurse -File -Filter 'llama-server.exe' | Select-Object -First 1
            if (-not $serverExe) { throw 'O pacote baixado não contém llama-server.exe.' }
            $stagedFiles = Get-ChildItem $stageDir -Recurse -File
            if (-not $stagedFiles) { throw 'Nenhum arquivo extraído do pacote do llama.cpp.' }
            L "[OK] Pacote validado ($($stagedFiles.Count) arquivos)"

            P 62 'Preparando troca segura'
            $llamaRoot = Join-Path $ROOT 'llamacpp-server'
            $llamaDir = Join-Path $llamaRoot 'bin'
            if (-not (Test-Path $llamaRoot)) { New-Item $llamaRoot -ItemType Directory -Force | Out-Null }
            if (-not (Test-Path $llamaDir)) { New-Item $llamaDir -ItemType Directory -Force | Out-Null }
            $backupDir = Join-Path $env:TEMP "neve_llama_backup_$([guid]::NewGuid().ToString('N'))"
            New-Item $backupDir -ItemType Directory -Force | Out-Null
            Get-ChildItem $llamaDir -Force -EA SilentlyContinue | ForEach-Object {
                Copy-Item $_.FullName $backupDir -Recurse -Force
            }
            L '[OK] Backup temporário criado'

            try {
                Get-Process llama-server -EA SilentlyContinue | Stop-Process -Force -EA SilentlyContinue
                Get-ChildItem $llamaDir -File -EA SilentlyContinue |
                    Where-Object { $_.Extension -in '.exe','.dll','.pdb' } |
                    Remove-Item -Force -EA Stop

                foreach ($file in $stagedFiles) {
                    Copy-Item $file.FullName $llamaDir -Force -EA Stop
                }

                if (-not (Test-Path (Join-Path $llamaDir 'llama-server.exe'))) {
                    throw 'llama-server.exe não ficou disponível após a cópia.'
                }
            } catch {
                $replaceError = $_
                L "[!] Falha ao aplicar binários; restaurando backup: $replaceError" 'warn'
                try {
                    Get-ChildItem $llamaDir -Force -EA SilentlyContinue | Remove-Item -Recurse -Force -EA SilentlyContinue
                    Get-ChildItem $backupDir -Force -EA SilentlyContinue | ForEach-Object {
                        Copy-Item $_.FullName $llamaDir -Recurse -Force
                    }
                    L '[OK] Backup restaurado'
                } catch {
                    L "[!] Falha ao restaurar backup automaticamente: $_" 'warn'
                }
                throw $replaceError
            }

            P 90 'Registrando versão'
            Set-Content -Path (Join-Path $llamaRoot 'version.txt') -Value @(
                $tag,
                $target.Label,
                $mainAsset.name
            ) -Encoding UTF8

            P 100 'llama.cpp atualizado'
            L "[OK] llama.cpp $tag instalado em llamacpp-server\bin"

            $summary = "Release: $tag`r`nBackend: $($target.Label)`r`nAsset:   $($mainAsset.name)"
            if ($runtimeAsset) { $summary += "`r`nRuntime: $($runtimeAsset.name)" }
            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.UpdatePanel.Visibility = 'Collapsed'
                $script:Ctl.DonePanel.Visibility   = 'Visible'
                $script:Ctl.LblDoneTitle.Text = 'llama.cpp atualizado!'
                $script:Ctl.LblDoneSub.Text   = 'Atualização opcional concluída sem alterar o projeto principal.'
                $script:Ctl.LblSummary.Text   = $summary
                $script:Ctl.BtnPrimary.Content   = 'Concluir'
                $script:Ctl.BtnPrimary.Tag       = 'done'
                $script:Ctl.BtnPrimary.IsEnabled = $true
                $script:Ctl.BtnLlama.IsEnabled   = $false
                $script:Ctl.BtnCancel.IsEnabled  = $false
            })
        } catch {
            $errMsg = "$_"
            L "[X] FALHA: $errMsg" 'err'
            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.LblStep.Text = 'Falha ao atualizar llama.cpp.'
                $script:Ctl.BtnPrimary.Content   = 'Fechar'
                $script:Ctl.BtnPrimary.Tag       = 'close'
                $script:Ctl.BtnPrimary.IsEnabled = $true
                $script:Ctl.BtnLlama.IsEnabled   = $true
                [System.Windows.MessageBox]::Show(
                    "A atualização do llama.cpp falhou.`r`n`r`nVeja o log em logs\update.log`r`n`r`n$errMsg",
                    'Neve AI - Atualizador',
                    [System.Windows.MessageBoxButton]::OK,
                    [System.Windows.MessageBoxImage]::Error) | Out-Null
            })
        } finally {
            foreach ($tmp in $tmpFiles) { try { Remove-Item $tmp -Force -EA SilentlyContinue } catch {} }
            if ($stageDir) { try { Remove-Item $stageDir -Recurse -Force -EA SilentlyContinue } catch {} }
            if ($backupDir) { try { Remove-Item $backupDir -Recurse -Force -EA SilentlyContinue } catch {} }
        }
    }

    $rs = [RunspaceFactory]::CreateRunspace()
    $rs.ApartmentState = 'STA'
    $rs.ThreadOptions  = 'ReuseThread'
    $rs.Open()
    $rs.SessionStateProxy.SetVariable('Window', $window)
    $rs.SessionStateProxy.SetVariable('Ctl',    $ctl)

    $ps = [PowerShell]::Create()
    $ps.Runspace = $rs
    [void]$ps.AddScript($worker)
    [void]$ps.AddArgument($argRoot)
    [void]$ps.AddArgument($argLog)
    [void]$ps.AddArgument($argLlamaApi)
    [void]$ps.AddArgument($argUa)
    [void]$ps.BeginInvoke()
})

# =============================================================================
# Versão instalada
# =============================================================================
$currentVersion = 'desconhecida'
if (Test-Path $VERSION_FILE) {
    $currentVersion = (Get-Content $VERSION_FILE -Raw).Trim()
    if (-not $currentVersion) { $currentVersion = 'desconhecida' }
}

$llamaVersionFile = Join-Path $ROOT 'llamacpp-server\version.txt'
$llamaInstalledTag = ''
$llamaInstalledBackend = ''
$llamaInstalledAsset = ''
if (Test-Path $llamaVersionFile) {
    $llamaLines = @(Get-Content $llamaVersionFile -EA SilentlyContinue)
    if ($llamaLines.Count -gt 0) { $llamaInstalledTag = $llamaLines[0].Trim() }
    if ($llamaLines.Count -gt 1) { $llamaInstalledBackend = $llamaLines[1].Trim() }
    if ($llamaLines.Count -gt 2) { $llamaInstalledAsset = $llamaLines[2].Trim() }
}

$llamaCurrentDisplay = 'Não instalado'
if ($llamaInstalledTag) {
    $llamaCurrentDisplay = $llamaInstalledTag
    if ($llamaInstalledBackend) { $llamaCurrentDisplay = "$llamaInstalledTag ($llamaInstalledBackend)" }
}

# =============================================================================
# Consulta a release mais recente (síncrono, antes de mostrar)
# =============================================================================
$latestTag   = $null
$releaseObj  = $null
$checkError  = $null
$llamaLatestTag = $null
$llamaReleaseObj = $null
$llamaCheckError = $null
try {
    $releaseObj = Invoke-RestMethod $API_LATEST -Headers @{ 'User-Agent' = $UA } -TimeoutSec 20
    $latestTag  = $releaseObj.tag_name
} catch {
    $checkError = "$_"
}
try {
    $llamaReleaseObj = Invoke-RestMethod $LLAMA_API_LATEST -Headers @{ 'User-Agent' = $UA } -TimeoutSec 20
    $llamaLatestTag  = $llamaReleaseObj.tag_name
} catch {
    $llamaCheckError = "$_"
}

$ctl.LblCurrent.Text = $currentVersion
if ($checkError) {
    $ctl.LblCheckTitle.Text = 'Falha ao verificar atualizações'
    $ctl.LblCheckSub.Text   = 'Não foi possível consultar o GitHub. Veja os detalhes abaixo.'
    $ctl.LblLatest.Text     = '—'
    $ctl.LblStatus.Text     = 'Erro de rede'
    $ctl.LblStatus.Foreground = '#DC2626'
    $ctl.LblNotes.Text      = $checkError
    $ctl.ChkUpdateNeve.Visibility = 'Collapsed'
} else {
    $ctl.LblLatest.Text = $latestTag
    $notes = $releaseObj.body
    if ([string]::IsNullOrWhiteSpace($notes)) { $notes = '(sem notas de release)' }
    $ctl.LblNotes.Text = $notes
    if ($currentVersion -eq $latestTag) {
        $ctl.LblStatus.Text     = 'Atualizado'
        $ctl.LblStatus.Foreground = '#10B981'
        $ctl.ChkUpdateNeve.Visibility = 'Collapsed'
    } else {
        $ctl.LblStatus.Text     = 'Atualização disponível'
        $ctl.LblStatus.Foreground = '#D97706'
        $ctl.ChkUpdateNeve.Visibility = 'Visible'
        $ctl.ChkUpdateNeve.IsChecked = $false
    }
}

$ctl.LblLlamaCurrent.Text = $llamaCurrentDisplay
if ($llamaCheckError) {
    $ctl.LblLlamaLatest.Text = '—'
    $ctl.LblLlamaStatus.Text = 'Erro ao verificar'
    $ctl.LblLlamaStatus.Foreground = '#DC2626'
    $ctl.ChkUpdateLlama.Visibility = 'Collapsed'
} else {
    $ctl.LblLlamaLatest.Text = $llamaLatestTag
    if ($llamaInstalledTag -and $llamaInstalledTag -eq $llamaLatestTag) {
        $ctl.LblLlamaStatus.Text = 'Atualizado'
        $ctl.LblLlamaStatus.Foreground = '#10B981'
        $ctl.ChkUpdateLlama.Visibility = 'Collapsed'
    } elseif ($llamaInstalledTag) {
        $ctl.LblLlamaStatus.Text = 'Atualização disponível'
        $ctl.LblLlamaStatus.Foreground = '#D97706'
        $ctl.ChkUpdateLlama.Visibility = 'Visible'
        $ctl.ChkUpdateLlama.IsChecked = $false
    } else {
        $ctl.LblLlamaStatus.Text = 'Não instalado'
        $ctl.LblLlamaStatus.Foreground = '#D97706'
        $ctl.ChkUpdateLlama.Visibility = 'Visible'
        $ctl.ChkUpdateLlama.IsChecked = $false
    }
}

if ($ctl.ChkUpdateNeve.Visibility -eq 'Visible' -and $ctl.ChkUpdateLlama.Visibility -eq 'Visible') {
    $ctl.LblCheckTitle.Text = 'Atualizações disponíveis'
    $ctl.LblCheckSub.Text = 'Marque uma ou mais atualizações para continuar.'
} elseif ($ctl.ChkUpdateNeve.Visibility -eq 'Visible') {
    $ctl.LblCheckTitle.Text = 'Atualização disponível'
    $ctl.LblCheckSub.Text = 'Uma nova versão está pronta para ser instalada.'
} elseif ($ctl.ChkUpdateLlama.Visibility -eq 'Visible') {
    $ctl.LblCheckTitle.Text = 'Atualização disponível'
    $ctl.LblCheckSub.Text = 'Uma nova versão está pronta para ser instalada.'
} elseif (-not $checkError -and -not $llamaCheckError) {
    $ctl.LblCheckTitle.Text = 'Você já está atualizado'
    $ctl.LblCheckSub.Text = 'Nenhuma atualização pendente para a Neve AI ou llama.cpp.'
}

Update-PrimaryButtonState

# =============================================================================
# Worker da atualização combinada (Neve AI -> llama.cpp)
# =============================================================================
$ctl.BtnPrimary.Add_Click({
    $tag = $ctl.BtnPrimary.Tag
    if ($tag -eq 'close')  { $window.Close(); return }
    if ($tag -eq 'done')   { $window.Close(); return }
    if ($tag -ne 'update') { return }

    $updateNeve  = [bool]$ctl.ChkUpdateNeve.IsChecked
    $updateLlama = [bool]$ctl.ChkUpdateLlama.IsChecked
    if (-not $updateNeve -and -not $updateLlama) { return }

    $ctl.CheckPanel.Visibility   = 'Collapsed'
    $ctl.UpdatePanel.Visibility  = 'Visible'
    $ctl.BtnPrimary.IsEnabled = $false
    $ctl.BtnLlama.IsEnabled   = $false
    $ctl.BtnCancel.IsEnabled  = $false
    $ctl.ChkUpdateNeve.IsEnabled = $false
    $ctl.ChkUpdateLlama.IsEnabled = $false

    $argUpdateNeve   = $updateNeve
    $argUpdateLlama  = $updateLlama
    $argLatestTag    = $latestTag
    $argZipUrl       = if ($releaseObj) { $releaseObj.zipball_url } else { $null }
    $argRoot         = $ROOT
    $argLog          = $LOG
    $argVersionFile  = $VERSION_FILE
    $argCurrent      = $currentVersion
    $argLlamaApi     = $LLAMA_API_LATEST
    $argUa           = $UA

    $worker = {
        param($updateNeve, $updateLlama, $latestTag, $zipUrl, $ROOT, $LOG, $VERSION_FILE, $currentVersion, $LLAMA_API_LATEST, $UA)

        function L([string]$m, [string]$k='info') {
            $ts = (Get-Date).ToString('HH:mm:ss')
            $line = "[$ts] $m"
            Add-Content -Path $LOG -Value $line -Encoding UTF8
            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.LogBox.AppendText($line + "`r`n")
                $script:Ctl.LogScroll.ScrollToEnd()
            })
        }
        function P([int]$v, [string]$phase) {
            if ($v -lt 0) { $v = 0 }
            if ($v -gt 100) { $v = 100 }
            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.Progress.Value = $v
                $script:Ctl.LblProgressTxt.Text = "$v%"
                if ($phase) { $script:Ctl.LblPhase.Text = $phase; $script:Ctl.LblStep.Text = $phase }
            })
        }
        function PN([int]$v, [string]$phase) {
            if ($updateLlama) { P ([int][math]::Round($v * 0.70)) $phase } else { P $v $phase }
        }
        function PL([int]$v, [string]$phase) {
            if ($updateNeve) { P (70 + [int][math]::Round($v * 0.30)) $phase } else { P $v $phase }
        }
        function Run([string]$exe, [string[]]$argv, [string]$desc) {
            L "==> $desc"
            $psi = New-Object System.Diagnostics.ProcessStartInfo
            $psi.FileName = $exe
            foreach ($a in $argv) { [void]$psi.ArgumentList.Add($a) }
            $psi.WorkingDirectory = $ROOT
            $psi.RedirectStandardOutput = $true
            $psi.RedirectStandardError  = $true
            $psi.UseShellExecute        = $false
            $psi.CreateNoWindow         = $true
            $p = [System.Diagnostics.Process]::Start($psi)
            while (-not $p.HasExited) {
                while (-not $p.StandardOutput.EndOfStream) {
                    $line = $p.StandardOutput.ReadLine()
                    if ($line) { L "    $line" }
                }
                Start-Sleep -Milliseconds 80
            }
            $rest = $p.StandardOutput.ReadToEnd()
            if ($rest) { foreach ($l in $rest -split "`r?`n") { if ($l) { L "    $l" } } }
            $err  = $p.StandardError.ReadToEnd()
            if ($err)  { foreach ($l in $err  -split "`r?`n") { if ($l) { L "    $l" 'warn' } } }
            return $p.ExitCode
        }
        function New-LlamaTarget([string]$vendor, [string]$name, [string]$label, [string[]]$backends, [string]$reason) {
            [pscustomobject]@{ Vendor=$vendor; Name=$name; Label=$label; Backends=$backends; Reason=$reason }
        }
        function Convert-ToInvariantDouble([string]$value) {
            if ([string]::IsNullOrWhiteSpace($value)) { return $null }
            try { return [double]::Parse(($value.Trim() -replace ',', '.'), [System.Globalization.CultureInfo]::InvariantCulture) } catch { return $null }
        }
        function Get-InstalledLlamaInfo([string]$root) {
            $versionPath = Join-Path $root 'llamacpp-server\version.txt'
            $tag = ''; $backend = ''; $asset = ''
            if (Test-Path $versionPath) {
                $lines = @(Get-Content $versionPath -EA SilentlyContinue)
                if ($lines.Count -gt 0) { $tag = $lines[0].Trim() }
                if ($lines.Count -gt 1) { $backend = $lines[1].Trim() }
                if ($lines.Count -gt 2) { $asset = $lines[2].Trim() }
            }
            [pscustomobject]@{ Tag=$tag; Backend=$backend; Asset=$asset }
        }
        function Get-LlamaHardwareTarget {
            $nvidiaLine = $null
            try {
                $nvidiaOut = nvidia-smi --query-gpu=name,compute_cap --format=csv,noheader 2>&1
                if ($LASTEXITCODE -eq 0 -and "$nvidiaOut" -notmatch 'failed|not found|invalid') {
                    $nvidiaLine = ("$nvidiaOut" -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -First 1)
                }
            } catch {}
            if (-not $nvidiaLine) {
                try {
                    $nvidiaOut = nvidia-smi --query-gpu=name --format=csv,noheader 2>&1
                    if ($LASTEXITCODE -eq 0 -and "$nvidiaOut" -notmatch 'failed|not found|invalid') {
                        $nameOnly = ("$nvidiaOut" -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -First 1).Trim()
                        if ($nameOnly) { $nvidiaLine = $nameOnly }
                    }
                } catch {}
            }
            if ($nvidiaLine) {
                $parts = $nvidiaLine -split ','
                $name = $parts[0].Trim()
                $computeCap = $null
                if ($parts.Count -gt 1) { $computeCap = Convert-ToInvariantDouble $parts[1] }
                if ($computeCap -ne $null -and $computeCap -lt 5.0) {
                    return New-LlamaTarget 'CPU' $name 'CPU (GPU NVIDIA sem suporte CUDA moderno)' @('cpu') "GPU NVIDIA detectada ($name), mas compute capability $computeCap não é suportada pelos binários CUDA atuais."
                }
                if ($name -match 'RTX\s*5\d{3}|50\d{2}|Blackwell' -or ($computeCap -ne $null -and $computeCap -ge 12.0)) {
                    return New-LlamaTarget 'NVIDIA' $name 'NVIDIA CUDA 13.1' @('cuda-13.1','cuda-cu13.1') "GPU NVIDIA Blackwell detectada: $name."
                }
                if ($computeCap -ne $null -and $computeCap -ge 5.0) {
                    return New-LlamaTarget 'NVIDIA' $name 'NVIDIA CUDA 12.4' @('cuda-12.4','cuda-cu12.4') "GPU NVIDIA compatível com CUDA 12 detectada: $name."
                }
                if ($name -match 'RTX\s*[234]\d{3}|[234]0\d{2}|GTX\s*16\d{2}|GTX\s*10\d{2}|GTX\s*9\d{2}|Quadro|Tesla|RTX\s*A') {
                    return New-LlamaTarget 'NVIDIA' $name 'NVIDIA CUDA 12.4' @('cuda-12.4','cuda-cu12.4') "GPU NVIDIA reconhecida por geração: $name."
                }
                throw "GPU NVIDIA detectada ($name), mas não foi possível determinar com segurança o binário CUDA correto. Nada foi instalado."
            }
            try {
                $gpus = Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name -EA SilentlyContinue
                $amdGpu = $gpus | Where-Object { $_ -match 'AMD|Radeon|RX\s' } | Select-Object -First 1
                if ($amdGpu) { return New-LlamaTarget 'AMD' $amdGpu.Trim() 'AMD Vulkan' @('vulkan') "GPU AMD detectada: $($amdGpu.Trim())." }
            } catch {}
            return New-LlamaTarget 'CPU' '' 'CPU' @('cpu') 'Nenhuma GPU NVIDIA/AMD compatível foi detectada.'
        }
        function Find-LlamaBinAsset($assets, [string]$tag, [string[]]$backends) {
            $tagEsc = [regex]::Escape($tag)
            foreach ($backend in $backends) {
                $backendEsc = [regex]::Escape($backend)
                $match = $assets | Where-Object { $_.name -match "^llama-$tagEsc-bin-win-$backendEsc-x64\.zip$" } | Select-Object -First 1
                if ($match) { return $match }
            }
            foreach ($backend in $backends) {
                $backendEsc = [regex]::Escape($backend)
                $match = $assets | Where-Object { $_.name -match "^llama-.+-bin-win-$backendEsc-x64\.zip$" } | Select-Object -First 1
                if ($match) { return $match }
            }
            return $null
        }
        function Find-CudaRuntimeAsset($assets, [string[]]$backends) {
            foreach ($backend in $backends) {
                $backendEsc = [regex]::Escape($backend)
                $match = $assets | Where-Object { $_.name -match "^cudart-llama-bin-win-$backendEsc-x64\.zip$" } | Select-Object -First 1
                if ($match) { return $match }
            }
            return $null
        }
        function Update-NeveAI {
            if (-not $latestTag -or -not $zipUrl) { throw 'Release do Neve AI indisponível para atualização.' }
            PN 5 "Baixando Neve AI $latestTag"
            L "==> Download $zipUrl"
            $tmpZip = Join-Path $env:TEMP "neve_update_$($latestTag).zip"
            if (Test-Path $tmpZip) { Remove-Item $tmpZip -Force }
            Invoke-WebRequest $zipUrl -OutFile $tmpZip -UseBasicParsing -Headers @{ 'User-Agent' = 'Neve-Updater/1.0' }
            $sizeMB = [math]::Round((Get-Item $tmpZip).Length / 1MB, 1)
            L "[OK] Neve AI baixado ($sizeMB MB)"

            PN 18 'Extraindo Neve AI'
            $tmpExt = Join-Path $env:TEMP "neve_update_ext_$($latestTag)"
            if (Test-Path $tmpExt) { Remove-Item $tmpExt -Recurse -Force }
            New-Item $tmpExt -ItemType Directory | Out-Null
            Expand-Archive $tmpZip -DestinationPath $tmpExt -Force
            $inner = Get-ChildItem $tmpExt -Directory | Select-Object -First 1
            if (-not $inner) { throw 'Estrutura inesperada do zip da release.' }

            PN 28 'Preservando configurações locais'
            $envFile = Join-Path $ROOT '.env'
            $envBackup = $null
            if (Test-Path $envFile) {
                $envBackup = Join-Path $env:TEMP "neve_update_env_$([guid]::NewGuid().ToString('N')).bak"
                Copy-Item $envFile $envBackup -Force
                L '[OK] .env preservado'
            }

            PN 35 'Aplicando arquivos do Neve AI'
            $excludeDirs = @('backend\neveai\venv','backend\neveai\frontend','backend\neveai\data','backend\data','backend\__pycache__','models','mmproj','llamacpp-server','node_modules','build','logs','.git','.svelte-kit')
            $excludeFiles = @('.env', 'version.txt')
            $rcArgs = @($inner.FullName, $ROOT, '/E', '/NFL', '/NDL', '/NP', '/NJH', '/NJS', '/R:1', '/W:1')
            $rcArgs += '/XD'
            foreach ($d in $excludeDirs) { $rcArgs += (Join-Path $ROOT $d) }
            $rcArgs += '/XF'
            foreach ($f in $excludeFiles) { $rcArgs += $f }
            $rcExit = Run 'robocopy' $rcArgs 'Copiando arquivos da release do Neve AI'
            if ($rcExit -ge 8) { throw "robocopy falhou com código $rcExit" }
            if ($envBackup -and -not (Test-Path $envFile)) { Copy-Item $envBackup $envFile -Force; L '[OK] .env restaurado' }
            if ($envBackup) { Remove-Item $envBackup -Force -EA SilentlyContinue }

            PN 55 'Instalando dependências do frontend'
            $npmCmd = Get-Command npm.cmd -EA SilentlyContinue
            if (-not $npmCmd) { $npmCmd = Get-Command npm -EA SilentlyContinue }
            if (-not $npmCmd) { throw 'npm não encontrado no PATH' }
            $npmExe = $npmCmd.Source
            $rc = Run $npmExe @('install', '--no-audit', '--no-fund') 'npm install'
            if ($rc -ne 0) { throw "npm install falhou (código $rc)" }

            PN 78 'Gerando build do frontend'
            $rc = Run $npmExe @('run', 'build') 'npm run build'
            if ($rc -ne 0) { throw "npm run build falhou (código $rc)" }

            PN 92 'Publicando frontend'
            $buildDir = Join-Path $ROOT 'build'
            $deployDir = Join-Path $ROOT 'backend\neveai\frontend'
            if (-not (Test-Path $buildDir)) { throw 'Pasta build\ não foi gerada' }
            if (Test-Path $deployDir) { Remove-Item $deployDir -Recurse -Force }
            New-Item $deployDir -ItemType Directory | Out-Null
            Copy-Item (Join-Path $buildDir '*') $deployDir -Recurse -Force

            PN 97 'Salvando versão do Neve AI'
            Set-Content -Path $VERSION_FILE -Value $latestTag -Encoding UTF8
            try { Remove-Item $tmpZip -Force -EA SilentlyContinue } catch {}
            try { Remove-Item $tmpExt -Recurse -Force -EA SilentlyContinue } catch {}
            L "[OK] Neve AI atualizado para $latestTag"
            return "Neve AI: $currentVersion -> $latestTag"
        }
        function Update-LlamaCpp {
            $tmpFiles = @(); $stageDir = $null; $backupDir = $null
            try {
                PL 5 'Consultando release do llama.cpp'
                $rel = Invoke-RestMethod $LLAMA_API_LATEST -Headers @{ 'User-Agent' = $UA } -TimeoutSec 30
                $tag = $rel.tag_name
                if (-not $tag) { throw 'Release do llama.cpp sem tag_name.' }
                $installed = Get-InstalledLlamaInfo $ROOT
                if ($installed.Tag -and $installed.Tag -eq $tag) {
                    L "[OK] llama.cpp já está na última release ($tag). Nenhum download necessário."
                    return "llama.cpp: já atualizado ($tag)"
                }

                PL 15 'Detectando hardware para llama.cpp'
                $target = Get-LlamaHardwareTarget
                L "[OK] Alvo llama.cpp: $($target.Label)"
                if ($target.Name) { L "    Hardware: $($target.Name)" }

                $mainAsset = Find-LlamaBinAsset $rel.assets $tag ([string[]]$target.Backends)
                if (-not $mainAsset) { throw "O release $tag não contém um asset Windows x64 para $($target.Label). Nada foi instalado." }
                $isCuda = (@($target.Backends) | Where-Object { $_ -match '^cuda' } | Select-Object -First 1) -ne $null
                $runtimeAsset = $null
                if ($isCuda) { $runtimeAsset = Find-CudaRuntimeAsset $rel.assets ([string[]]$target.Backends) }

                PL 28 'Baixando llama.cpp'
                $tmpMain = Join-Path $env:TEMP "neve_llama_$([guid]::NewGuid().ToString('N')).zip"
                $tmpFiles += $tmpMain
                Invoke-WebRequest $mainAsset.browser_download_url -OutFile $tmpMain -UseBasicParsing -Headers @{ 'User-Agent' = $UA }
                $tmpRuntime = $null
                if ($runtimeAsset) {
                    $tmpRuntime = Join-Path $env:TEMP "neve_llama_cudart_$([guid]::NewGuid().ToString('N')).zip"
                    $tmpFiles += $tmpRuntime
                    Invoke-WebRequest $runtimeAsset.browser_download_url -OutFile $tmpRuntime -UseBasicParsing -Headers @{ 'User-Agent' = $UA }
                }

                PL 45 'Extraindo e validando llama.cpp'
                $stageDir = Join-Path $env:TEMP "neve_llama_stage_$([guid]::NewGuid().ToString('N'))"
                New-Item $stageDir -ItemType Directory -Force | Out-Null
                Expand-Archive $tmpMain -DestinationPath $stageDir -Force
                if ($tmpRuntime) { Expand-Archive $tmpRuntime -DestinationPath $stageDir -Force }
                $serverExe = Get-ChildItem $stageDir -Recurse -File -Filter 'llama-server.exe' | Select-Object -First 1
                if (-not $serverExe) { throw 'O pacote baixado não contém llama-server.exe.' }
                $stagedFiles = Get-ChildItem $stageDir -Recurse -File
                if (-not $stagedFiles) { throw 'Nenhum arquivo extraído do pacote do llama.cpp.' }

                PL 62 'Instalando llama.cpp'
                $llamaRoot = Join-Path $ROOT 'llamacpp-server'
                $llamaDir = Join-Path $llamaRoot 'bin'
                if (-not (Test-Path $llamaRoot)) { New-Item $llamaRoot -ItemType Directory -Force | Out-Null }
                if (-not (Test-Path $llamaDir)) { New-Item $llamaDir -ItemType Directory -Force | Out-Null }
                $backupDir = Join-Path $env:TEMP "neve_llama_backup_$([guid]::NewGuid().ToString('N'))"
                New-Item $backupDir -ItemType Directory -Force | Out-Null
                Get-ChildItem $llamaDir -Force -EA SilentlyContinue | ForEach-Object { Copy-Item $_.FullName $backupDir -Recurse -Force }
                try {
                    Get-Process llama-server -EA SilentlyContinue | Stop-Process -Force -EA SilentlyContinue
                    Get-ChildItem $llamaDir -File -EA SilentlyContinue | Where-Object { $_.Extension -in '.exe','.dll','.pdb' } | Remove-Item -Force -EA Stop
                    foreach ($file in $stagedFiles) { Copy-Item $file.FullName $llamaDir -Force -EA Stop }
                    if (-not (Test-Path (Join-Path $llamaDir 'llama-server.exe'))) { throw 'llama-server.exe não ficou disponível após a cópia.' }
                } catch {
                    $replaceError = $_
                    L "[!] Falha ao aplicar llama.cpp; restaurando backup: $replaceError" 'warn'
                    try {
                        Get-ChildItem $llamaDir -Force -EA SilentlyContinue | Remove-Item -Recurse -Force -EA SilentlyContinue
                        Get-ChildItem $backupDir -Force -EA SilentlyContinue | ForEach-Object { Copy-Item $_.FullName $llamaDir -Recurse -Force }
                    } catch {}
                    throw $replaceError
                }

                PL 90 'Registrando versão do llama.cpp'
                Set-Content -Path (Join-Path $llamaRoot 'version.txt') -Value @($tag, $target.Label, $mainAsset.name) -Encoding UTF8
                L "[OK] llama.cpp $tag instalado"
                return "llama.cpp: $($installed.Tag -replace '^$','não instalado') -> $tag ($($target.Label))"
            } finally {
                foreach ($tmp in $tmpFiles) { try { Remove-Item $tmp -Force -EA SilentlyContinue } catch {} }
                if ($stageDir) { try { Remove-Item $stageDir -Recurse -Force -EA SilentlyContinue } catch {} }
                if ($backupDir) { try { Remove-Item $backupDir -Recurse -Force -EA SilentlyContinue } catch {} }
            }
        }

        try {
            $summary = @()
            if ($updateNeve) { $summary += Update-NeveAI }
            if ($updateLlama) { $summary += Update-LlamaCpp }
            P 100 'Concluído'
            L '[OK] Atualização concluída.'

            $doneTitle = if ($updateNeve -and $updateLlama) { 'Atualizações concluídas!' } elseif ($updateNeve) { 'Neve AI atualizado!' } else { 'llama.cpp atualizado!' }
            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.UpdatePanel.Visibility = 'Collapsed'
                $script:Ctl.DonePanel.Visibility   = 'Visible'
                $script:Ctl.LblDoneTitle.Text = $doneTitle
                $script:Ctl.LblDoneSub.Text   = 'Use start.bat para iniciar o Neve AI.'
                $script:Ctl.LblSummary.Text   = ($summary -join "`r`n")
                $script:Ctl.BtnPrimary.Content   = 'Concluir'
                $script:Ctl.BtnPrimary.Tag       = 'done'
                $script:Ctl.BtnPrimary.IsEnabled = $true
                $script:Ctl.BtnPrimary.Visibility = 'Visible'
                $script:Ctl.BtnCancel.IsEnabled  = $false
            })
        } catch {
            $errMsg = "$_"
            L "[X] FALHA: $errMsg" 'err'
            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.LblStep.Text = 'Falha durante a atualização.'
                $script:Ctl.BtnPrimary.Content   = 'Fechar'
                $script:Ctl.BtnPrimary.Tag       = 'close'
                $script:Ctl.BtnPrimary.IsEnabled = $true
                $script:Ctl.BtnPrimary.Visibility = 'Visible'
                [System.Windows.MessageBox]::Show(
                    "A atualização falhou.`r`n`r`nVeja o log em logs\update.log`r`n`r`n$errMsg",
                    'Neve AI - Atualizador',
                    [System.Windows.MessageBoxButton]::OK,
                    [System.Windows.MessageBoxImage]::Error) | Out-Null
            })
        }
    }

    $rs = [RunspaceFactory]::CreateRunspace()
    $rs.ApartmentState = 'STA'
    $rs.ThreadOptions  = 'ReuseThread'
    $rs.Open()
    $rs.SessionStateProxy.SetVariable('Window', $window)
    $rs.SessionStateProxy.SetVariable('Ctl',    $ctl)

    $ps = [PowerShell]::Create()
    $ps.Runspace = $rs
    [void]$ps.AddScript($worker)
    [void]$ps.AddArgument($argUpdateNeve)
    [void]$ps.AddArgument($argUpdateLlama)
    [void]$ps.AddArgument($argLatestTag)
    [void]$ps.AddArgument($argZipUrl)
    [void]$ps.AddArgument($argRoot)
    [void]$ps.AddArgument($argLog)
    [void]$ps.AddArgument($argVersionFile)
    [void]$ps.AddArgument($argCurrent)
    [void]$ps.AddArgument($argLlamaApi)
    [void]$ps.AddArgument($argUa)
    [void]$ps.BeginInvoke()
})

# =============================================================================
# Mostra a janela
# =============================================================================
[void]$window.ShowDialog()
