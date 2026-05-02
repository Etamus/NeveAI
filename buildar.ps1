# Neve AI - Buildar Grafico (WPF)
# Faz build limpo, publica em backend\neveai\frontend e valida o hash do index.html.

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase
Add-Type -AssemblyName System.Windows.Forms

# =============================================================================
# Caminhos globais
# =============================================================================
$ROOT = Split-Path $MyInvocation.MyCommand.Path -Parent
$BUILD_DIR = Join-Path $ROOT 'build'
$DEPLOY_DIR = Join-Path $ROOT 'backend\neveai\frontend'
$LOG_DIR = Join-Path $ROOT 'logs'
if (-not (Test-Path $LOG_DIR)) { New-Item $LOG_DIR -ItemType Directory | Out-Null }
$LOG = Join-Path $LOG_DIR 'build.log'
'' | Set-Content $LOG -Encoding UTF8

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
        Title="Neve AI - Buildar"
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
                            <Trigger Property="IsEnabled" Value="False">
                                <Setter TargetName="bd" Property="Opacity" Value="0.5"/>
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

            <Grid Grid.Row="0" Background="Transparent">
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="Auto"/>
                    <ColumnDefinition Width="*"/>
                    <ColumnDefinition Width="Auto"/>
                </Grid.ColumnDefinitions>
                <StackPanel Grid.Column="0" Orientation="Horizontal" Margin="18,0,0,0" VerticalAlignment="Center">
                    <Image x:Name="LogoImg" Width="22" Height="22" Margin="0,0,10,0"/>
                    <TextBlock Text="Neve AI" FontSize="15" FontWeight="SemiBold" Foreground="#111111" VerticalAlignment="Center"/>
                    <TextBlock Text="  -  Buildar" FontSize="13" Foreground="#71717A" VerticalAlignment="Center"/>
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

            <Grid Grid.Row="1" Margin="32,8,32,0">
                <Grid x:Name="IntroPanel">
                    <Grid.RowDefinitions>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="*"/>
                    </Grid.RowDefinitions>

                    <StackPanel Grid.Row="0" Margin="0,0,0,18">
                        <TextBlock Text="Build e deploy do frontend" FontSize="22" FontWeight="SemiBold" Foreground="#111111"/>
                        <TextBlock Text="Compila o projeto e publica a pasta build no backend da Neve AI."
                                   FontSize="13" Foreground="#71717A" Margin="0,4,0,0"/>
                    </StackPanel>

                    <Border Grid.Row="1" Background="White" CornerRadius="10" BorderBrush="#E4E4E7" BorderThickness="1" Padding="20">
                        <Grid>
                            <Grid.RowDefinitions>
                                <RowDefinition Height="Auto"/>
                                <RowDefinition Height="Auto"/>
                                <RowDefinition Height="Auto"/>
                                <RowDefinition Height="Auto"/>
                            </Grid.RowDefinitions>
                            <Grid.ColumnDefinitions>
                                <ColumnDefinition Width="170"/>
                                <ColumnDefinition Width="*"/>
                            </Grid.ColumnDefinitions>

                            <TextBlock Grid.Row="0" Grid.Column="0" Text="Build:" FontSize="13" Foreground="#52525B" Margin="0,0,0,12"/>
                            <TextBlock Grid.Row="0" Grid.Column="1" x:Name="LblBuildPath" Text="build" FontSize="13" FontWeight="SemiBold" Foreground="#111111" Margin="0,0,0,12" TextTrimming="CharacterEllipsis"/>

                            <TextBlock Grid.Row="1" Grid.Column="0" Text="Destino:" FontSize="13" Foreground="#52525B" Margin="0,0,0,12"/>
                            <TextBlock Grid.Row="1" Grid.Column="1" x:Name="LblDeployPath" Text="backend\neveai\frontend" FontSize="13" FontWeight="SemiBold" Foreground="#111111" Margin="0,0,0,12" TextTrimming="CharacterEllipsis"/>

                            <TextBlock Grid.Row="2" Grid.Column="0" Text="Comando:" FontSize="13" Foreground="#52525B" Margin="0,0,0,12"/>
                            <TextBlock Grid.Row="2" Grid.Column="1" Text="npm run build" FontSize="13" FontWeight="SemiBold" Foreground="#111111" Margin="0,0,0,12"/>

                            <Border Grid.Row="3" Grid.ColumnSpan="2" Background="#FAFAFA" CornerRadius="8" Padding="14,12" Margin="0,8,0,0">
                                <StackPanel>
                                    <TextBlock Text="O que sera feito:" FontWeight="SemiBold" FontSize="13" Foreground="#111111" Margin="0,0,0,4"/>
                                    <TextBlock Text="- Limpar a pasta build antiga" FontSize="12" Foreground="#52525B"/>
                                    <TextBlock Text="- Rodar npm run build" FontSize="12" Foreground="#52525B"/>
                                    <TextBlock Text="- Limpar backend\neveai\frontend" FontSize="12" Foreground="#52525B"/>
                                    <TextBlock Text="- Copiar build para o backend" FontSize="12" Foreground="#52525B"/>
                                    <TextBlock Text="- Conferir o hash do index.html publicado" FontSize="12" Foreground="#52525B"/>
                                </StackPanel>
                            </Border>
                        </Grid>
                    </Border>
                </Grid>

                <Grid x:Name="WorkPanel" Visibility="Collapsed">
                    <Grid.RowDefinitions>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="*"/>
                    </Grid.RowDefinitions>

                    <StackPanel Grid.Row="0" Margin="0,0,0,12">
                        <TextBlock Text="Buildando..." FontSize="22" FontWeight="SemiBold" Foreground="#111111"/>
                        <TextBlock x:Name="LblStep" Text="Preparando..." FontSize="13" Foreground="#71717A" Margin="0,4,0,0"/>
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

                <Grid x:Name="DonePanel" Visibility="Collapsed">
                    <Border Background="White" CornerRadius="10" BorderBrush="#E4E4E7" BorderThickness="1" Padding="32">
                        <StackPanel HorizontalAlignment="Center" VerticalAlignment="Center">
                            <Border x:Name="StatusBadge" Width="56" Height="56" CornerRadius="28" Background="#10B981" Margin="0,0,0,18">
                                <TextBlock x:Name="LblBadge" Text="OK" FontSize="20" FontWeight="Bold" Foreground="White" HorizontalAlignment="Center" VerticalAlignment="Center"/>
                            </Border>
                            <TextBlock x:Name="LblDoneTitle" Text="Build publicado!" FontSize="22" FontWeight="SemiBold" Foreground="#111111" HorizontalAlignment="Center"/>
                            <TextBlock x:Name="LblDoneSub" Text="O frontend do backend esta atualizado." FontSize="13" Foreground="#71717A" HorizontalAlignment="Center" Margin="0,6,0,18"/>
                            <Border Background="#FAFAFA" CornerRadius="8" Padding="14,12" MaxWidth="620">
                                <TextBlock x:Name="LblSummary" FontFamily="Consolas" FontSize="11" Foreground="#52525B" TextWrapping="Wrap"/>
                            </Border>
                        </StackPanel>
                    </Border>
                </Grid>
            </Grid>

            <Border Grid.Row="2" BorderBrush="#EEEEEE" BorderThickness="0,1,0,0" Padding="32,0,32,0">
                <StackPanel Orientation="Horizontal" HorizontalAlignment="Right" VerticalAlignment="Center">
                    <Button x:Name="BtnCancel" Style="{StaticResource GhostBtn}" Content="Cancelar" Margin="0,0,10,0"/>
                    <Button x:Name="BtnPrimary" Style="{StaticResource PrimaryBtn}" Content="Buildar e publicar"/>
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
foreach ($name in 'LogoImg','BtnClose','IntroPanel','WorkPanel','DonePanel',
                  'LblBuildPath','LblDeployPath','LblStep','LblPhase','LblProgressTxt',
                  'Progress','LogBox','LogScroll','StatusBadge','LblBadge','LblDoneTitle',
                  'LblDoneSub','LblSummary','BtnCancel','BtnPrimary') {
    $ctl[$name] = $window.FindName($name)
}

$ctl.LblBuildPath.Text = $BUILD_DIR
$ctl.LblDeployPath.Text = $DEPLOY_DIR

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

$script:IsRunning = $false

function Set-UI([scriptblock]$sb) {
    [void]$window.Dispatcher.Invoke([Action]$sb)
}

function Append-Log([string]$msg, [string]$kind = 'info') {
    $ts = (Get-Date).ToString('HH:mm:ss')
    $prefix = switch ($kind) {
        'ok'    { '[OK] ' }
        'warn'  { '[!]  ' }
        'err'   { '[X]  ' }
        'step'  { '==>  ' }
        default { '     ' }
    }
    $line = "[$ts] $prefix$msg"
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
        if ($phase) {
            $ctl.LblPhase.Text = $phase
            $ctl.LblStep.Text = $phase
        }
    }
}

function ConvertTo-ProcessArgument([string]$arg) {
    if ($null -eq $arg) { return '""' }
    if ($arg -notmatch '[\s"]') { return $arg }
    return '"' + ($arg -replace '"', '\"') + '"'
}

function Invoke-LoggedProcess([string]$fileName, [string[]]$arguments, [string]$description) {
    Append-Log $description 'step'
    Append-Log ("> " + $fileName + ' ' + ($arguments -join ' '))

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $fileName
    $psi.Arguments = ($arguments | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' '
    $psi.WorkingDirectory = $ROOT
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    $proc.EnableRaisingEvents = $true

    $outHandler = [System.Diagnostics.DataReceivedEventHandler]{
        param($sender, $eventArgs)
        if ($eventArgs.Data) { Append-Log $eventArgs.Data }
    }
    $errHandler = [System.Diagnostics.DataReceivedEventHandler]{
        param($sender, $eventArgs)
        if ($eventArgs.Data) { Append-Log $eventArgs.Data 'warn' }
    }

    $proc.add_OutputDataReceived($outHandler)
    $proc.add_ErrorDataReceived($errHandler)

    [void]$proc.Start()
    $proc.BeginOutputReadLine()
    $proc.BeginErrorReadLine()
    $proc.WaitForExit()
    $proc.WaitForExit()

    $proc.remove_OutputDataReceived($outHandler)
    $proc.remove_ErrorDataReceived($errHandler)

    if ($proc.ExitCode -eq 0) {
        Append-Log "$description concluido" 'ok'
    } else {
        Append-Log "$description falhou com codigo $($proc.ExitCode)" 'err'
    }

    return $proc.ExitCode
}

function Set-Done([bool]$ok, [string]$summary) {
    Set-UI {
        $ctl.IntroPanel.Visibility = 'Collapsed'
        $ctl.WorkPanel.Visibility = 'Collapsed'
        $ctl.DonePanel.Visibility = 'Visible'
        $ctl.BtnCancel.Visibility = 'Collapsed'
        $ctl.BtnPrimary.Tag = 'close'
        $ctl.BtnPrimary.Content = 'Fechar'
        $ctl.BtnPrimary.IsEnabled = $true

        if ($ok) {
            $ctl.StatusBadge.Background = New-Object System.Windows.Media.SolidColorBrush ([System.Windows.Media.ColorConverter]::ConvertFromString('#10B981'))
            $ctl.LblBadge.Text = 'OK'
            $ctl.LblDoneTitle.Text = 'Build publicado!'
            $ctl.LblDoneSub.Text = 'O frontend do backend esta atualizado.'
        } else {
            $ctl.StatusBadge.Background = New-Object System.Windows.Media.SolidColorBrush ([System.Windows.Media.ColorConverter]::ConvertFromString('#EF4444'))
            $ctl.LblBadge.Text = 'X'
            $ctl.LblDoneTitle.Text = 'Build falhou'
            $ctl.LblDoneSub.Text = 'Confira o log para ver o ponto da falha.'
        }

        $ctl.LblSummary.Text = $summary
    }
}

function Start-BuildDeploy {
    if ($script:IsRunning) { return }
    $script:IsRunning = $true

    Set-UI {
        $ctl.IntroPanel.Visibility = 'Collapsed'
        $ctl.DonePanel.Visibility = 'Collapsed'
        $ctl.WorkPanel.Visibility = 'Visible'
        $ctl.LogBox.Clear()
        $ctl.Progress.Value = 0
        $ctl.LblProgressTxt.Text = '0%'
        $ctl.LblPhase.Text = 'Preparando'
        $ctl.LblStep.Text = 'Preparando build...'
        $ctl.BtnPrimary.IsEnabled = $false
        $ctl.BtnCancel.IsEnabled = $false
    }

    $worker = New-Object System.ComponentModel.BackgroundWorker

    $worker.add_DoWork({
        param($sender, $eventArgs)
        try {
            Set-Location $ROOT

            Set-Progress 5 'Verificando npm'
            $npmCmd = Get-Command npm.cmd -EA SilentlyContinue
            if (-not $npmCmd) { $npmCmd = Get-Command npm -EA SilentlyContinue }
            if (-not $npmCmd) { throw 'npm nao encontrado no PATH.' }
            $npmExe = $npmCmd.Source
            Append-Log "npm: $npmExe" 'ok'

            Set-Progress 12 'Limpando build antigo'
            if (Test-Path $BUILD_DIR) {
                Remove-Item $BUILD_DIR -Recurse -Force
                Append-Log 'Pasta build antiga removida' 'ok'
            } else {
                Append-Log 'Nenhuma pasta build antiga encontrada'
            }

            Set-Progress 22 'Executando npm run build'
            $rc = Invoke-LoggedProcess $npmExe @('run', 'build') 'npm run build'
            if ($rc -ne 0) { throw "npm run build falhou (codigo $rc)." }

            $srcIndex = Join-Path $BUILD_DIR 'index.html'
            if (-not (Test-Path $srcIndex)) { throw 'build\index.html nao foi gerado.' }

            Set-Progress 82 'Limpando destino do backend'
            if (Test-Path $DEPLOY_DIR) {
                Get-ChildItem -LiteralPath $DEPLOY_DIR -Force | Remove-Item -Recurse -Force
                Append-Log 'Destino backend\neveai\frontend limpo' 'ok'
            } else {
                New-Item $DEPLOY_DIR -ItemType Directory -Force | Out-Null
                Append-Log 'Destino backend\neveai\frontend criado' 'ok'
            }

            Set-Progress 88 'Copiando build para o backend'
            Copy-Item -Path (Join-Path $BUILD_DIR '*') -Destination $DEPLOY_DIR -Recurse -Force
            Append-Log 'Arquivos copiados para backend\neveai\frontend' 'ok'

            Set-Progress 94 'Verificando hash do deploy'
            $dstIndex = Join-Path $DEPLOY_DIR 'index.html'
            if (-not (Test-Path $dstIndex)) { throw 'backend\neveai\frontend\index.html nao foi publicado.' }
            $srcHash = Get-FileHash $srcIndex -Algorithm SHA256
            $dstHash = Get-FileHash $dstIndex -Algorithm SHA256
            if ($srcHash.Hash -ne $dstHash.Hash) { throw 'Hash do index.html nao bate entre build e deploy.' }
            Append-Log 'deploy hash match' 'ok'

            $fileCount = (Get-ChildItem -LiteralPath $DEPLOY_DIR -Recurse -File | Measure-Object).Count
            Set-Progress 100 'Concluido'

            $eventArgs.Result = [pscustomobject]@{
                Ok = $true
                Summary = "Build:  $BUILD_DIR`nDeploy: $DEPLOY_DIR`nArquivos publicados: $fileCount`nSHA256 index.html: $($srcHash.Hash)"
            }
        } catch {
            Append-Log $_.Exception.Message 'err'
            $eventArgs.Result = [pscustomobject]@{
                Ok = $false
                Summary = "Erro: $($_.Exception.Message)`nLog:  $LOG"
            }
        }
    })

    $worker.add_RunWorkerCompleted({
        param($sender, $eventArgs)
        $script:IsRunning = $false
        $result = $eventArgs.Result
        if ($result -and $result.Ok) {
            Set-Done $true $result.Summary
        } else {
            $summary = if ($result) { $result.Summary } else { "Erro desconhecido.`nLog: $LOG" }
            Set-Done $false $summary
        }
    })

    $worker.RunWorkerAsync()
}

$ctl.BtnClose.Add_Click({ if (-not $script:IsRunning) { $window.Close() } })
$ctl.BtnCancel.Add_Click({ if (-not $script:IsRunning) { $window.Close() } })
$ctl.BtnPrimary.Add_Click({
    if ($ctl.BtnPrimary.Tag -eq 'close') {
        $window.Close()
    } else {
        Start-BuildDeploy
    }
})

[void]$window.ShowDialog()
