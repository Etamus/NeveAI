# Neve AI - Buildar Grafico (WPF)
# Faz build limpo, publica em backend\neveai\frontend e valida o hash do index.html.

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase
Add-Type -AssemblyName System.Windows.Forms

# =============================================================================
# Caminhos globais
# =============================================================================
$SCRIPT_PATH = if ($PSCommandPath) { $PSCommandPath } elseif ($MyInvocation.MyCommand.Path) { $MyInvocation.MyCommand.Path } else { throw 'Não foi possível determinar o caminho do build.' }
$ROOT = (Resolve-Path -LiteralPath (Split-Path -Parent $SCRIPT_PATH)).ProviderPath
Set-Location -LiteralPath $ROOT
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
                            <TextBlock Grid.Row="2" Grid.Column="1" Text="npm portatil run build" FontSize="13" FontWeight="SemiBold" Foreground="#111111" Margin="0,0,0,12"/>

                            <Border Grid.Row="3" Grid.ColumnSpan="2" Background="#FAFAFA" CornerRadius="8" Padding="14,12" Margin="0,8,0,0">
                                <StackPanel>
                                    <TextBlock Text="O que sera feito:" FontWeight="SemiBold" FontSize="13" Foreground="#111111" Margin="0,0,0,4"/>
                                    <TextBlock Text="- Limpar a pasta build antiga" FontSize="12" Foreground="#52525B"/>
                                    <TextBlock Text="- Preparar Node.js/npm portatil se necessario" FontSize="12" Foreground="#52525B"/>
                                    <TextBlock Text="- Instalar pacotes npm se estiverem ausentes" FontSize="12" Foreground="#52525B"/>
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
$script:ExitCode = 0

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

    $npmCache = Join-Path $ROOT 'tools\npm-cache'
    if (-not (Test-Path -LiteralPath $npmCache)) { New-Item -ItemType Directory -Path $npmCache -Force | Out-Null }
    $psi.EnvironmentVariables['npm_config_cache'] = $npmCache
    $psi.EnvironmentVariables['npm_config_audit'] = 'false'
    $psi.EnvironmentVariables['npm_config_fund'] = 'false'
    $psi.EnvironmentVariables['npm_config_update_notifier'] = 'false'

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi

    try {
        [void]$proc.Start()
    } catch {
        throw "Falha ao iniciar '$fileName' para '$description': $($_.Exception.Message)"
    }

    $stdoutTask = $proc.StandardOutput.ReadToEndAsync()
    $stderrTask = $proc.StandardError.ReadToEndAsync()
    $proc.WaitForExit()
    $stdoutTask.Wait()
    $stderrTask.Wait()

    foreach ($line in [regex]::Split($stdoutTask.Result, "\r?\n")) {
        if (-not [string]::IsNullOrWhiteSpace($line)) { Append-Log $line }
    }
    foreach ($line in [regex]::Split($stderrTask.Result, "\r?\n")) {
        if (-not [string]::IsNullOrWhiteSpace($line)) { Append-Log $line 'warn' }
    }

    if ($proc.ExitCode -eq 0) {
        Append-Log "$description concluido" 'ok'
    } else {
        Append-Log "$description falhou com codigo $($proc.ExitCode)" 'err'
    }

    return $proc.ExitCode
}

function Get-NodeMajorFromVersion([string]$version) {
    if ([string]::IsNullOrWhiteSpace($version)) { return -1 }
    if ($version -notmatch '^v?(\d+)\.') { return -1 }
    return [int]$matches[1]
}

function Test-FrontendNodePair([string]$nodeExe, [string]$npmExe) {
    try {
        if ([string]::IsNullOrWhiteSpace($nodeExe) -or -not (Test-Path -LiteralPath $nodeExe)) { return $null }
        if ([string]::IsNullOrWhiteSpace($npmExe) -or -not (Test-Path -LiteralPath $npmExe)) { return $null }

        $nodePath = (Resolve-Path -LiteralPath $nodeExe).ProviderPath
        if ($nodePath -match '\\Microsoft\\WindowsApps\\node\.exe$') { return $null }

        $nodeVersionOut = & $nodePath --version 2>&1
        if ($LASTEXITCODE -ne 0) { return $null }
        $nodeVersion = (("$nodeVersionOut" -split "`r?`n") | Where-Object { $_.Trim() } | Select-Object -First 1).Trim()
        $nodeMajor = Get-NodeMajorFromVersion $nodeVersion
        if ($nodeMajor -lt 18 -or $nodeMajor -gt 22) { return $null }

        $npmPath = (Resolve-Path -LiteralPath $npmExe).ProviderPath
        $npmVersionOut = & $npmPath --version 2>&1
        if ($LASTEXITCODE -ne 0) { return $null }
        $npmVersion = (("$npmVersionOut" -split "`r?`n") | Where-Object { $_.Trim() } | Select-Object -First 1).Trim()
        if (-not $npmVersion) { return $null }

        return [pscustomobject]@{
            NodeExecutable = $nodePath
            NodeVersion    = $nodeVersion
            NpmExecutable  = $npmPath
            NpmVersion     = $npmVersion
            NodeDir        = Split-Path -Parent $nodePath
        }
    } catch {
        return $null
    }
}

function Resolve-FrontendNodeLaunch {
    $nodeCandidates = @()
    $portableNode = Join-Path $ROOT 'tools\nodejs\node.exe'
    if (Test-Path -LiteralPath $portableNode) { $nodeCandidates += $portableNode }
    if ($env:NODE_EXE) { $nodeCandidates += $env:NODE_EXE }

    foreach ($cmd in @(Get-Command node.exe -All -EA SilentlyContinue)) {
        $nodeCandidates += $cmd.Source
    }

    foreach ($nodeBase in (@($env:ProgramFiles, ${env:ProgramFiles(x86)}) | Where-Object { $_ })) {
        $path = Join-Path $nodeBase 'nodejs\node.exe'
        if (Test-Path -LiteralPath $path) { $nodeCandidates += $path }
    }

    foreach ($nodeCandidate in ($nodeCandidates | Select-Object -Unique)) {
        $nodeDir = Split-Path -Parent $nodeCandidate
        foreach ($npmName in @('npm.cmd', 'npm.exe')) {
            $npmPath = Join-Path $nodeDir $npmName
            $pair = Test-FrontendNodePair $nodeCandidate $npmPath
            if ($pair) { return $pair }
        }
    }

    return $null
}

function Install-PortableNode22 {
    Set-Progress 8 'Preparando Node.js portatil'
    $toolsDir = Join-Path $ROOT 'tools'
    $nodeDir = Join-Path $toolsDir 'nodejs'

    $existing = Test-FrontendNodePair (Join-Path $nodeDir 'node.exe') (Join-Path $nodeDir 'npm.cmd')
    if ($existing) {
        Append-Log "Node.js portatil ja disponivel: $($existing.NodeVersion) / npm $($existing.NpmVersion)" 'ok'
        return $existing
    }

    if (-not (Test-Path -LiteralPath $toolsDir)) { New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null }
    Append-Log 'Baixando Node.js 22 LTS portatil porque nenhum Node.js 18-22 valido foi encontrado' 'step'

    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13
    } catch {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    }

    $release = $null
    try {
        $index = Invoke-RestMethod 'https://nodejs.org/dist/index.json' -Headers @{ 'User-Agent' = 'Neve-Buildar/1.0' } -TimeoutSec 60
        $release = $index | Where-Object { $_.version -match '^v22\.' -and $_.files -contains 'win-x64-zip' } | Select-Object -First 1
    } catch {
        Append-Log "Falha ao consultar versoes do Node.js: $($_.Exception.Message)" 'warn'
    }

    if (-not $release) { throw 'Nao foi possivel encontrar Node.js 22 win-x64 no site oficial.' }

    $version = [string]$release.version
    $url = "https://nodejs.org/dist/$version/node-$version-win-x64.zip"
    $zipPath = Join-Path $env:TEMP "neve_node_$version.zip"
    $stageParent = Join-Path $env:TEMP "neve_node_stage_$([guid]::NewGuid().ToString('N'))"
    $stageTarget = Join-Path $toolsDir "nodejs-stage-$([guid]::NewGuid().ToString('N'))"

    try {
        if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force -EA SilentlyContinue }
        New-Item -ItemType Directory -Path $stageParent -Force | Out-Null
        Append-Log "Baixando $url"
        Invoke-WebRequest $url -OutFile $zipPath -UseBasicParsing -Headers @{ 'User-Agent' = 'Neve-Buildar/1.0' } -TimeoutSec 300

        Append-Log 'Extraindo Node.js portatil'
        Expand-Archive $zipPath -DestinationPath $stageParent -Force
        $extracted = Get-ChildItem -LiteralPath $stageParent -Directory | Select-Object -First 1
        if (-not $extracted) { throw 'Arquivo do Node.js nao extraiu a pasta esperada.' }
        Move-Item -LiteralPath $extracted.FullName -Destination $stageTarget -Force

        $stagedPair = Test-FrontendNodePair (Join-Path $stageTarget 'node.exe') (Join-Path $stageTarget 'npm.cmd')
        if (-not $stagedPair) { throw 'Node.js portatil extraido nao passou na validacao.' }

        if (Test-Path -LiteralPath $nodeDir) { Remove-Item -LiteralPath $nodeDir -Recurse -Force -EA SilentlyContinue }
        Move-Item -LiteralPath $stageTarget -Destination $nodeDir -Force

        $pair = Test-FrontendNodePair (Join-Path $nodeDir 'node.exe') (Join-Path $nodeDir 'npm.cmd')
        if (-not $pair) { throw 'Node.js portatil foi copiado, mas nao respondeu apos a instalacao.' }
        Append-Log "Node.js portatil pronto: $($pair.NodeVersion) / npm $($pair.NpmVersion)" 'ok'
        return $pair
    } finally {
        try { if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force -EA SilentlyContinue } } catch {}
        try { if (Test-Path -LiteralPath $stageParent) { Remove-Item -LiteralPath $stageParent -Recurse -Force -EA SilentlyContinue } } catch {}
        try { if (Test-Path -LiteralPath $stageTarget) { Remove-Item -LiteralPath $stageTarget -Recurse -Force -EA SilentlyContinue } } catch {}
    }
}

function Resolve-OrInstallFrontendNode {
    $frontendNode = Resolve-FrontendNodeLaunch
    if (-not $frontendNode) { $frontendNode = Install-PortableNode22 }
    if (-not $frontendNode) { throw 'Node.js 18-22 com npm nao encontrado e o Node.js 22 portatil nao pode ser preparado.' }

    $env:PATH = "$($frontendNode.NodeDir);$env:PATH"
    $env:npm_config_cache = Join-Path $ROOT 'tools\npm-cache'
    $env:npm_config_audit = 'false'
    $env:npm_config_fund = 'false'
    $env:npm_config_update_notifier = 'false'

    Append-Log "Node.js do build: $($frontendNode.NodeVersion) / npm $($frontendNode.NpmVersion) em $($frontendNode.NodeDir)" 'ok'
    return $frontendNode
}

function Test-FrontendDependencies {
    $vite = Join-Path $ROOT 'node_modules\vite\bin\vite.js'
    $svelteKit = Join-Path $ROOT 'node_modules\@sveltejs\kit\package.json'
    return ((Test-Path -LiteralPath $vite) -and (Test-Path -LiteralPath $svelteKit))
}

function Ensure-FrontendDependencies([string]$npmExe) {
    if (Test-FrontendDependencies) {
        Append-Log 'Pacotes npm ja estao presentes' 'ok'
        return
    }

    Set-Progress 15 'Instalando pacotes npm'
    $rc = Invoke-LoggedProcess $npmExe @('install', '--no-audit', '--no-fund') 'npm install'
    if ($rc -ne 0) { throw "npm install falhou (codigo $rc)." }
}

function Set-Done([bool]$ok, [string]$summary) {
    $script:ExitCode = if ($ok) { 0 } else { 1 }

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

    try {
        Set-Location -LiteralPath $ROOT
        Append-Log "Pasta do build: $ROOT" 'ok'

        Set-Progress 5 'Preparando Node.js/npm'
        $frontendNode = Resolve-OrInstallFrontendNode
        $npmExe = $frontendNode.NpmExecutable

        Ensure-FrontendDependencies $npmExe

        Set-Progress 22 'Limpando build antigo'
        if (Test-Path $BUILD_DIR) {
            Remove-Item $BUILD_DIR -Recurse -Force
            Append-Log 'Pasta build antiga removida' 'ok'
        } else {
            Append-Log 'Nenhuma pasta build antiga encontrada'
        }

        Set-Progress 32 'Executando npm run build'
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

        $script:IsRunning = $false
        Set-Done $true "Build:  $BUILD_DIR`nDeploy: $DEPLOY_DIR`nArquivos publicados: $fileCount`nSHA256 index.html: $($srcHash.Hash)"
    } catch {
        Append-Log $_.Exception.Message 'err'
        $script:IsRunning = $false
        Set-Done $false "Erro: $($_.Exception.Message)`nLog:  $LOG"
    }
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
exit $script:ExitCode
