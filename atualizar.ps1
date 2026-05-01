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
                                <RowDefinition Height="Auto"/>
                                <RowDefinition Height="Auto"/>
                                <RowDefinition Height="*"/>
                            </Grid.RowDefinitions>
                            <Grid.ColumnDefinitions>
                                <ColumnDefinition Width="180"/>
                                <ColumnDefinition Width="*"/>
                            </Grid.ColumnDefinitions>

                            <TextBlock Grid.Row="0" Grid.Column="0" Text="Versão instalada:" FontSize="13" Foreground="#52525B" Margin="0,0,0,12"/>
                            <TextBlock Grid.Row="0" Grid.Column="1" x:Name="LblCurrent" Text="—" FontSize="13" FontWeight="SemiBold" Foreground="#111111" Margin="0,0,0,12"/>

                            <TextBlock Grid.Row="1" Grid.Column="0" Text="Última disponível:" FontSize="13" Foreground="#52525B" Margin="0,0,0,12"/>
                            <TextBlock Grid.Row="1" Grid.Column="1" x:Name="LblLatest" Text="—" FontSize="13" FontWeight="SemiBold" Foreground="#111111" Margin="0,0,0,12"/>

                            <TextBlock Grid.Row="2" Grid.Column="0" Text="Status:" FontSize="13" Foreground="#52525B" Margin="0,0,0,12"/>
                            <TextBlock Grid.Row="2" Grid.Column="1" x:Name="LblStatus" Text="Aguardando…" FontSize="13" FontWeight="SemiBold" Foreground="#71717A" Margin="0,0,0,12"/>

                            <TextBlock Grid.Row="3" Grid.ColumnSpan="2" Text="Notas da release:" FontSize="13" FontWeight="SemiBold" Foreground="#111111" Margin="0,8,0,6"/>

                            <Border Grid.Row="4" Grid.ColumnSpan="2" Background="#FAFAFA" CornerRadius="8" Padding="12,10">
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
                    <Button x:Name="BtnCancel" Style="{StaticResource GhostBtn}" Content="Cancelar" Margin="0,0,10,0"/>
                    <Button x:Name="BtnPrimary" Style="{StaticResource PrimaryBtn}" Content="Atualizar" IsEnabled="False"/>
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

# =============================================================================
# Versão instalada
# =============================================================================
$currentVersion = 'desconhecida'
if (Test-Path $VERSION_FILE) {
    $currentVersion = (Get-Content $VERSION_FILE -Raw).Trim()
    if (-not $currentVersion) { $currentVersion = 'desconhecida' }
}

# =============================================================================
# Consulta a release mais recente (síncrono, antes de mostrar)
# =============================================================================
$latestTag   = $null
$releaseObj  = $null
$checkError  = $null
try {
    $releaseObj = Invoke-RestMethod $API_LATEST -Headers @{ 'User-Agent' = $UA } -TimeoutSec 20
    $latestTag  = $releaseObj.tag_name
} catch {
    $checkError = "$_"
}

$ctl.LblCurrent.Text = $currentVersion
if ($checkError) {
    $ctl.LblCheckTitle.Text = 'Falha ao verificar atualizações'
    $ctl.LblCheckSub.Text   = 'Não foi possível consultar o GitHub. Veja os detalhes abaixo.'
    $ctl.LblLatest.Text     = '—'
    $ctl.LblStatus.Text     = 'Erro de rede'
    $ctl.LblStatus.Foreground = '#DC2626'
    $ctl.LblNotes.Text      = $checkError
    $ctl.BtnPrimary.Content   = 'Fechar'
    $ctl.BtnPrimary.IsEnabled = $true
    $ctl.BtnPrimary.Tag       = 'close'
} else {
    $ctl.LblLatest.Text = $latestTag
    $notes = $releaseObj.body
    if ([string]::IsNullOrWhiteSpace($notes)) { $notes = '(sem notas de release)' }
    $ctl.LblNotes.Text = $notes
    if ($currentVersion -eq $latestTag) {
        $ctl.LblCheckTitle.Text = 'Você já está na última versão'
        $ctl.LblCheckSub.Text   = "Nenhuma atualização pendente. Versão atual: $currentVersion."
        $ctl.LblStatus.Text     = 'Atualizado'
        $ctl.LblStatus.Foreground = '#10B981'
        $ctl.BtnPrimary.Content   = 'Fechar'
        $ctl.BtnPrimary.IsEnabled = $true
        $ctl.BtnPrimary.Tag       = 'close'
    } else {
        $ctl.LblCheckTitle.Text = 'Atualização disponível'
        $ctl.LblCheckSub.Text   = "Uma nova versão do Neve AI está pronta para ser instalada."
        $ctl.LblStatus.Text     = "Pendente"
        $ctl.LblStatus.Foreground = '#D97706'
        $ctl.BtnPrimary.Content   = 'Atualizar'
        $ctl.BtnPrimary.IsEnabled = $true
        $ctl.BtnPrimary.Tag       = 'update'
    }
}

# =============================================================================
# Worker da atualização (executa em runspace)
# =============================================================================
$ctl.BtnPrimary.Add_Click({
    $tag = $ctl.BtnPrimary.Tag
    if ($tag -eq 'close')  { $window.Close(); return }
    if ($tag -eq 'done')   { $window.Close(); return }
    if ($tag -ne 'update') { return }

    # Troca de painel
    $ctl.CheckPanel.Visibility   = 'Collapsed'
    $ctl.UpdatePanel.Visibility  = 'Visible'
    $ctl.BtnPrimary.IsEnabled = $false
    $ctl.BtnCancel.IsEnabled  = $false

    $argLatestTag   = $latestTag
    $argZipUrl      = $releaseObj.zipball_url
    $argRoot        = $ROOT
    $argLog         = $LOG
    $argVersionFile = $VERSION_FILE
    $argCurrent     = $currentVersion

    $worker = {
        param($latestTag, $zipUrl, $ROOT, $LOG, $VERSION_FILE, $currentVersion)

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

        try {
            # ---- 1. Download
            P 5 "Baixando $latestTag"
            L "==> Download $zipUrl"
            $tmpZip = Join-Path $env:TEMP "neve_update_$($latestTag).zip"
            if (Test-Path $tmpZip) { Remove-Item $tmpZip -Force }
            Invoke-WebRequest $zipUrl -OutFile $tmpZip -UseBasicParsing -Headers @{ 'User-Agent' = 'Neve-Updater/1.0' }
            $sizeMB = [math]::Round((Get-Item $tmpZip).Length / 1MB, 1)
            L "[OK] Baixado ($sizeMB MB)"

            # ---- 2. Extração
            P 18 'Extraindo arquivos'
            $tmpExt = Join-Path $env:TEMP "neve_update_ext_$($latestTag)"
            if (Test-Path $tmpExt) { Remove-Item $tmpExt -Recurse -Force }
            New-Item $tmpExt -ItemType Directory | Out-Null
            Expand-Archive $tmpZip -DestinationPath $tmpExt -Force
            $inner = Get-ChildItem $tmpExt -Directory | Select-Object -First 1
            if (-not $inner) { throw "Estrutura inesperada do zip da release." }
            L "[OK] Extraído em $($inner.FullName)"

            # ---- 3. Backup leve do .env
            P 28 'Preservando configurações locais'
            $envFile = Join-Path $ROOT '.env'
            $envBackup = $null
            if (Test-Path $envFile) {
                $envBackup = Join-Path $env:TEMP "neve_update_env_$([guid]::NewGuid().ToString('N')).bak"
                Copy-Item $envFile $envBackup -Force
                L "[OK] .env preservado"
            }

            # ---- 4. Overlay com Robocopy (preserva venv, models, mmproj, llamacpp-server, node_modules, logs, data)
            P 35 'Aplicando arquivos novos'
            $excludeDirs = @(
                'backend\neveai\venv',
                'backend\neveai\frontend',
                'backend\neveai\data',
                'backend\data',
                'backend\__pycache__',
                'models',
                'mmproj',
                'llamacpp-server',
                'node_modules',
                'build',
                'logs',
                '.git',
                '.svelte-kit'
            )
            $excludeFiles = @('.env', 'version.txt')

            $rcArgs = @($inner.FullName, $ROOT, '/E', '/NFL', '/NDL', '/NP', '/NJH', '/NJS', '/R:1', '/W:1')
            $rcArgs += '/XD'
            foreach ($d in $excludeDirs) { $rcArgs += (Join-Path $ROOT $d) }
            $rcArgs += '/XF'
            foreach ($f in $excludeFiles) { $rcArgs += $f }

            L "==> robocopy (overlay)"
            $rcExit = Run 'robocopy' $rcArgs 'Copiando arquivos da release'
            # Robocopy: 0..7 = sucesso; 8+ = erro
            if ($rcExit -ge 8) { throw "robocopy falhou com código $rcExit" }
            L "[OK] Arquivos aplicados (robocopy=$rcExit)"

            # Restaura .env se algo apagou
            if ($envBackup -and -not (Test-Path $envFile)) {
                Copy-Item $envBackup $envFile -Force
                L "[OK] .env restaurado"
            }
            if ($envBackup) { Remove-Item $envBackup -Force -EA SilentlyContinue }

            # ---- 5. npm install
            P 55 'Instalando dependências do frontend (npm install)'
            $npmCmd = Get-Command npm.cmd -EA SilentlyContinue
            if (-not $npmCmd) { $npmCmd = Get-Command npm -EA SilentlyContinue }
            if (-not $npmCmd) { throw "npm não encontrado no PATH" }
            $npmExe = $npmCmd.Source
            $rc = Run $npmExe @('install', '--no-audit', '--no-fund') 'npm install'
            if ($rc -ne 0) { throw "npm install falhou (código $rc)" }

            # ---- 6. npm run build
            P 78 'Gerando build do frontend (npm run build)'
            $rc = Run $npmExe @('run', 'build') 'npm run build'
            if ($rc -ne 0) { throw "npm run build falhou (código $rc)" }

            # ---- 7. Deploy do build para o backend
            P 92 'Publicando build no backend'
            $buildDir = Join-Path $ROOT 'build'
            $deployDir = Join-Path $ROOT 'backend\neveai\frontend'
            if (-not (Test-Path $buildDir)) { throw "Pasta build\ não foi gerada" }
            if (Test-Path $deployDir) { Remove-Item $deployDir -Recurse -Force }
            New-Item $deployDir -ItemType Directory | Out-Null
            Copy-Item (Join-Path $buildDir '*') $deployDir -Recurse -Force
            L "[OK] Frontend publicado em backend\neveai\frontend"

            # ---- 8. Atualiza version.txt
            P 97 'Salvando nova versão'
            Set-Content -Path $VERSION_FILE -Value $latestTag -Encoding UTF8
            L "[OK] version.txt = $latestTag"

            # ---- 9. Limpeza temporária
            try { Remove-Item $tmpZip -Force -EA SilentlyContinue } catch {}
            try { Remove-Item $tmpExt -Recurse -Force -EA SilentlyContinue } catch {}

            P 100 'Concluído'
            L "[OK] Atualização concluída."

            $script:Window.Dispatcher.Invoke([Action]{
                $script:Ctl.UpdatePanel.Visibility = 'Collapsed'
                $script:Ctl.DonePanel.Visibility   = 'Visible'
                $script:Ctl.LblDoneTitle.Text = 'Atualização concluída!'
                $script:Ctl.LblDoneSub.Text   = "Use start.bat para iniciar o Neve AI."
                $script:Ctl.LblSummary.Text   = "Versão anterior : $currentVersion`r`nVersão instalada: $latestTag"
                $script:Ctl.BtnPrimary.Content   = 'Concluir'
                $script:Ctl.BtnPrimary.Tag       = 'done'
                $script:Ctl.BtnPrimary.IsEnabled = $true
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
    [void]$ps.AddArgument($argLatestTag)
    [void]$ps.AddArgument($argZipUrl)
    [void]$ps.AddArgument($argRoot)
    [void]$ps.AddArgument($argLog)
    [void]$ps.AddArgument($argVersionFile)
    [void]$ps.AddArgument($argCurrent)
    [void]$ps.BeginInvoke()
})

# =============================================================================
# Mostra a janela
# =============================================================================
[void]$window.ShowDialog()
