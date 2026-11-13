# Shared transactional update engine, extracted from the native installer.
function PN([int]$v, [string]$phase) {
            if ($updateLlama) { P ([int][math]::Round($v * 0.70)) $phase } else { P $v $phase }
        }

function PL([int]$v, [string]$phase) {
            if ($updateNeve) { P (70 + [int][math]::Round($v * 0.30)) $phase } else { P $v $phase }
        }

function Test-LlamaBackendCompatible([string]$requested, [string]$available) {
            if ([string]::IsNullOrWhiteSpace($requested) -or [string]::IsNullOrWhiteSpace($available)) { return $false }
            if ($requested -eq $available) { return $true }
            $requestedCuda = [regex]::Match($requested, '^cuda(?:-cu)?-?(\d+)(?:\.\d+)?$')
            $availableCuda = [regex]::Match($available, '^cuda(?:-cu)?-?(\d+)(?:\.\d+)?$')
            return ($requestedCuda.Success -and $availableCuda.Success -and $requestedCuda.Groups[1].Value -eq $availableCuda.Groups[1].Value)
        }

function Get-LatestLlamaRelease([string[]]$backends) {
            $apiError = $null
            try {
                $releases = @((Invoke-RestMethod $LLAMA_API_RELEASES -Headers @{ 'User-Agent' = $UA; 'Accept' = 'application/vnd.github+json' } -TimeoutSec 30))
                foreach ($release in $releases) {
                    if ($release.draft -or -not $release.tag_name) { continue }
                    $tagEsc = [regex]::Escape([string]$release.tag_name)
                    foreach ($asset in @($release.assets)) {
                        $assetMatch = [regex]::Match([string]$asset.name, "^llama-$tagEsc-bin-win-(.+)-x64\.zip$")
                        if (-not $assetMatch.Success) { continue }
                        $availableBackend = $assetMatch.Groups[1].Value
                        foreach ($backend in $backends) {
                            if (Test-LlamaBackendCompatible $backend $availableBackend) { return $release }
                        }
                    }
                }
                throw 'Nenhuma release recente do llama.cpp contém os binários Windows necessários.'
            } catch {
                $apiError = $_
            }

            try {
                $feed = Invoke-WebRequest 'https://github.com/ggml-org/llama.cpp/releases.atom' -Headers @{ 'User-Agent' = $UA } -UseBasicParsing -TimeoutSec 30
                $seenTags = @{}
                foreach ($match in [regex]::Matches([string]$feed.Content, '/releases/tag/([^"<]+)')) {
                    $tag = [uri]::UnescapeDataString($match.Groups[1].Value).Trim()
                    if (-not $tag -or $seenTags.ContainsKey($tag)) { continue }
                    $seenTags[$tag] = $true

                    foreach ($backend in $backends) {
                        $mainAsset = New-LlamaReleaseAsset $tag "llama-$tag-bin-win-$backend-x64.zip"
                        if (-not (Test-ReleaseAssetUrl $mainAsset.browser_download_url)) { continue }

                        $assets = @($mainAsset)
                        if ($backend -match '^cuda') {
                            $runtimeAsset = New-LlamaReleaseAsset $tag "cudart-llama-bin-win-$backend-x64.zip"
                            if (Test-ReleaseAssetUrl $runtimeAsset.browser_download_url) { $assets += $runtimeAsset }
                        }

                        L '[!] GitHub API limitada; usando o feed de releases compatíveis.' 'warn'
                        return [pscustomobject]@{ tag_name = $tag; assets = $assets; prerelease = $true; draft = $false; is_fallback = $true }
                    }
                }
            } catch {}

            throw "Não foi possível localizar uma release compatível do llama.cpp: $apiError"
        }

function New-LlamaReleaseAsset([string]$tag, [string]$name) {
            [pscustomobject]@{
                name = $name
                size = 0
                browser_download_url = "https://github.com/ggml-org/llama.cpp/releases/download/$([uri]::EscapeDataString($tag))/$([uri]::EscapeDataString($name))"
            }
        }

function Test-ReleaseAssetUrl([string]$url) {
            try {
                $request = [System.Net.HttpWebRequest]::Create($url)
                $request.Method = 'HEAD'
                $request.AllowAutoRedirect = $true
                $request.UserAgent = $UA
                $request.Timeout = 15000
                $response = $request.GetResponse()
                try {
                    $statusCode = [int]$response.StatusCode
                    return ($statusCode -ge 200 -and $statusCode -lt 400)
                } finally {
                    $response.Close()
                }
            } catch {
                return $false
            }
        }

function ConvertTo-ProcessArgument([string]$arg) {
            if ($null -eq $arg) { throw 'Argumento nulo.' }
            if ($arg.Length -gt 0 -and $arg -notmatch '[\s"]') { return $arg }
            $escaped = [regex]::Replace($arg, '(\\*)"', '$1$1\"')
            $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
            return '"' + $escaped + '"'
        }

function Run([string]$exe, [string[]]$argv, [string]$desc, [int]$timeoutSeconds = 3600) {
            L "==> $desc"
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
            $psi.RedirectStandardOutput = $true
            $psi.RedirectStandardError  = $true
            $psi.UseShellExecute        = $false
            $psi.CreateNoWindow         = $true
            $npmCache = Join-Path $ROOT 'tools\npm-cache'
            if (-not (Test-Path -LiteralPath $npmCache)) { New-Item -ItemType Directory -Path $npmCache -Force | Out-Null }
            $psi.EnvironmentVariables['npm_config_cache'] = $npmCache
            $psi.EnvironmentVariables['npm_config_audit'] = 'false'
            $psi.EnvironmentVariables['npm_config_fund'] = 'false'
            $psi.EnvironmentVariables['npm_config_update_notifier'] = 'false'
            if ($script:FrontendNodeDir) {
                try {
                    $currentPath = $psi.EnvironmentVariables['PATH']
                    if ([string]::IsNullOrWhiteSpace($currentPath)) { $currentPath = $env:PATH }
                    $psi.EnvironmentVariables['PATH'] = "$script:FrontendNodeDir;$currentPath"
                } catch {
                    L "[!] Não foi possível priorizar Node.js portátil para '$desc': $($_.Exception.Message)" 'warn'
                }
            }
            L ("> {0} {1}" -f $exe, ($safeArgs -join ' '))
            $p = $null
            try {
                $p = [System.Diagnostics.Process]::Start($psi)
            } catch {
                throw "Falha ao iniciar '$exe' para '$desc': $($_.Exception.Message)"
            }
            if ($null -eq $p) { throw "Falha ao iniciar '$exe' para '$desc': Process.Start retornou nulo." }
            if ($UPDATE_CONTROL -and $UPDATE_CONTROL.Processes) {
                [void]$UPDATE_CONTROL.Processes.Add($p)
            }

            # stdout e stderr precisam ser drenados ao mesmo tempo. Vite/Svelte escreve
            # muitos avisos em stderr durante "transforming..." e enche o pipe se apenas
            # stdout for lido, bloqueando tanto o build quanto o atualizador.
            $stdoutDone = $false
            $stderrDone = $false
            $stdoutTask = $p.StandardOutput.ReadLineAsync()
            $stderrTask = $p.StandardError.ReadLineAsync()
            $lastActivity = Get-Date
            $startedAt = Get-Date

            while (-not ($stdoutDone -and $stderrDone)) {
                if ($UPDATE_CONTROL -and $UPDATE_CONTROL.CancelRequested) {
                    try { if (-not $p.HasExited) { $p.Kill() } } catch {}
                    throw [System.OperationCanceledException]::new('Atualização cancelada pelo usuário.')
                }
                $readLine = $false

                if (-not $stdoutDone -and $stdoutTask.IsCompleted) {
                    $line = $stdoutTask.GetAwaiter().GetResult()
                    if ($null -eq $line) {
                        $stdoutDone = $true
                        $stdoutTask = $null
                    } else {
                        if (-not [string]::IsNullOrWhiteSpace($line)) { L "    $line" }
                        $lastActivity = Get-Date
                        $stdoutTask = $p.StandardOutput.ReadLineAsync()
                    }
                    $readLine = $true
                }

                if (-not $stderrDone -and $stderrTask.IsCompleted) {
                    $line = $stderrTask.GetAwaiter().GetResult()
                    if ($null -eq $line) {
                        $stderrDone = $true
                        $stderrTask = $null
                    } else {
                        if (-not [string]::IsNullOrWhiteSpace($line)) { L "    $line" 'warn' }
                        $lastActivity = Get-Date
                        $stderrTask = $p.StandardError.ReadLineAsync()
                    }
                    $readLine = $true
                }

                $now = Get-Date
                if (-not $p.HasExited -and $timeoutSeconds -gt 0 -and ($now - $startedAt).TotalSeconds -ge $timeoutSeconds) {
                    try { $p.Kill() } catch {}
                    try { $p.WaitForExit(5000) | Out-Null } catch {}
                    try { $p.Dispose() } catch {}
                    throw "Tempo limite excedido em '$desc' após $timeoutSeconds segundos. A atualização será restaurada."
                }
                if (-not $p.HasExited -and ($now - $lastActivity).TotalSeconds -ge 10) {
                    L "    ... $desc ainda em andamento."
                    $lastActivity = $now
                }

                if (-not $readLine) { Start-Sleep -Milliseconds 25 }
            }

            $p.WaitForExit()
            $exitCode = $p.ExitCode
            if ($UPDATE_CONTROL -and $UPDATE_CONTROL.Processes) {
                [void]$UPDATE_CONTROL.Processes.Remove($p)
            }
            $p.Dispose()
            return $exitCode
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
                $npmCliPath = Join-Path (Split-Path -Parent $nodePath) 'node_modules\npm\bin\npm-cli.js'
                if (Test-Path -LiteralPath $npmCliPath) {
                    $npmVersionOut = & $nodePath $npmCliPath --version 2>&1
                } else {
                    $npmVersionOut = & $npmPath --version 2>&1
                }
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
            $portableRoots = @(
                (Join-Path $ROOT 'tools'),
                (Join-Path $env:LocalAppData 'NeveAI\tools'),
                (Join-Path $env:TEMP 'NeveAI\tools')
            ) | Select-Object -Unique
            foreach ($portableRoot in $portableRoots) {
                $portableNode = Join-Path $portableRoot 'nodejs\node.exe'
                if (Test-Path -LiteralPath $portableNode) { $nodeCandidates += $portableNode }
                if (Test-Path -LiteralPath $portableRoot) {
                    $nodeCandidates += @(Get-ChildItem -LiteralPath $portableRoot -Directory -Filter 'nodejs-*' -EA SilentlyContinue |
                        ForEach-Object { Join-Path $_.FullName 'node.exe' } |
                        Where-Object { Test-Path -LiteralPath $_ })
                }
            }
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
                foreach ($npmName in @('npm.cmd','npm.exe')) {
                    $npmPath = Join-Path $nodeDir $npmName
                    $pair = Test-FrontendNodePair $nodeCandidate $npmPath
                    if ($pair) { return $pair }
                }
            }

            return $null
        }

function Install-PortableNode22 {
            P 52 'Preparando Node.js 22 portátil'
            $toolsDir = Join-Path $ROOT 'tools'
            $nodeDir = Join-Path $toolsDir 'nodejs'
            $existing = Test-FrontendNodePair (Join-Path $nodeDir 'node.exe') (Join-Path $nodeDir 'npm.cmd')
            if ($existing) {
                L "[OK] Node.js portátil já disponível: $($existing.NodeVersion) / npm $($existing.NpmVersion)"
                return $existing
            }

            if (-not (Test-Path -LiteralPath $toolsDir)) { New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null }
            L '==> Baixando Node.js 22 LTS portátil porque o Node do sistema está ausente ou fora da faixa suportada (18-22)'

            try {
                [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13
            } catch {
                [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            }

            $release = $null
            try {
                $index = Invoke-RestMethod 'https://nodejs.org/dist/index.json' -Headers @{ 'User-Agent' = $UA } -TimeoutSec 60
                $release = $index | Where-Object { $_.version -match '^v22\.' -and $_.files -contains 'win-x64-zip' } | Select-Object -First 1
            } catch {
                L "[!] Falha ao consultar versões do Node.js: $($_.Exception.Message)" 'warn'
            }
            if (-not $release) {
                $release = [pscustomobject]@{ version = 'v22.23.3'; files = @('win-x64-zip') }
                L '[!] Índice do Node.js indisponível; usando a versão LTS de fallback v22.23.3.' 'warn'
            }

            $version = [string]$release.version
            $url = "https://nodejs.org/dist/$version/node-$version-win-x64.zip"
            $zipPath = Join-Path $env:TEMP "neve_node_$version-$([guid]::NewGuid().ToString('N')).zip"
            $stageParent = Join-Path $env:TEMP "neve_node_stage_$([guid]::NewGuid().ToString('N'))"
            try {
                if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force -EA SilentlyContinue }
                New-Item -ItemType Directory -Path $stageParent -Force | Out-Null
                L "==> Baixando $url"
                try {
                    Invoke-WebRequest $url -OutFile $zipPath -UseBasicParsing -Headers @{ 'User-Agent' = $UA } -TimeoutSec 300
                } catch {
                    L "[!] Download pelo PowerShell falhou: $($_.Exception.Message). Tentando curl." 'warn'
                    $curl = Get-Command curl.exe -EA SilentlyContinue | Select-Object -First 1
                    if (-not $curl) { throw }
                    $rc = Run $curl.Source @('-L','--fail','--silent','--show-error','--compressed','--retry','3','--retry-delay','2','--connect-timeout','30','--max-time','300','--output',$zipPath,$url) 'Baixando Node.js com curl'
                    if ($rc -ne 0 -or -not (Test-Path -LiteralPath $zipPath) -or (Get-Item -LiteralPath $zipPath).Length -le 0) {
                        throw "curl não conseguiu baixar Node.js (exit $rc)."
                    }
                }
                Expand-Archive $zipPath -DestinationPath $stageParent -Force
                $extracted = Get-ChildItem -LiteralPath $stageParent -Directory | Select-Object -First 1
                if (-not $extracted) { throw 'Arquivo do Node.js não extraiu a pasta esperada.' }
                $stagedPair = Test-FrontendNodePair (Join-Path $extracted.FullName 'node.exe') (Join-Path $extracted.FullName 'npm.cmd')
                if (-not $stagedPair) { throw 'Node.js portátil extraído não passou na validação.' }

                $installParents = @(
                    $toolsDir,
                    (Join-Path $env:LocalAppData 'NeveAI\tools'),
                    (Join-Path $env:TEMP 'NeveAI\tools')
                ) | Select-Object -Unique
                $installErrors = @()
                foreach ($installParent in $installParents) {
                    $candidateDir = Join-Path $installParent 'nodejs'
                    $createdCandidate = $false
                    try {
                        if (-not (Test-Path -LiteralPath $installParent)) {
                            New-Item -ItemType Directory -Path $installParent -Force -EA Stop | Out-Null
                        }
                        $candidateExisting = Test-FrontendNodePair (Join-Path $candidateDir 'node.exe') (Join-Path $candidateDir 'npm.cmd')
                        if ($candidateExisting) { return $candidateExisting }
                        if (Test-Path -LiteralPath $candidateDir) {
                            try { Remove-Item -LiteralPath $candidateDir -Recurse -Force -EA Stop } catch {}
                            if (Test-Path -LiteralPath $candidateDir) {
                                $candidateDir = Join-Path $installParent ("nodejs-{0}-{1}" -f $version.TrimStart('v'), [guid]::NewGuid().ToString('N').Substring(0, 8))
                            }
                        }
                        $createdCandidate = $true
                        Copy-Item -LiteralPath $extracted.FullName -Destination $candidateDir -Recurse -Force -EA Stop
                        Get-ChildItem -LiteralPath $candidateDir -Recurse -File -EA SilentlyContinue | Unblock-File -EA SilentlyContinue

                        $pair = $null
                        for ($attempt = 1; $attempt -le 10 -and -not $pair; $attempt++) {
                            $pair = Test-FrontendNodePair (Join-Path $candidateDir 'node.exe') (Join-Path $candidateDir 'npm.cmd')
                            if (-not $pair) { Start-Sleep -Milliseconds 500 }
                        }
                        if (-not $pair) { throw 'Os arquivos foram copiados, mas Node.js/npm não responderam.' }
                        if ($candidateDir -ne $nodeDir) { L "[!] Node.js portátil instalado no fallback: $candidateDir" 'warn' }
                        L "[OK] Node.js portátil pronto: $($pair.NodeVersion) / npm $($pair.NpmVersion)"
                        return $pair
                    } catch {
                        $installErrors += "$candidateDir -> $($_.Exception.Message)"
                        L "[!] Não foi possível preparar Node.js em '$candidateDir': $($_.Exception.Message)" 'warn'
                        if ($createdCandidate) {
                            try { Remove-Item -LiteralPath $candidateDir -Recurse -Force -EA SilentlyContinue } catch {}
                        }
                    }
                }
                throw "Não foi possível preparar Node.js portátil em nenhum local permitido. $($installErrors -join ' | ')"
            } finally {
                try { if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force -EA SilentlyContinue } } catch {}
                try { if (Test-Path -LiteralPath $stageParent) { Remove-Item -LiteralPath $stageParent -Recurse -Force -EA SilentlyContinue } } catch {}
            }
        }

function Test-NeveAppIntegrity([string]$root) {
            $required = @(
                @{ Path = 'instalar.bat'; Label = 'instalar.bat' },
                @{ Path = 'launchers\instalar.ps1'; Label = 'launchers\instalar.ps1' },
                @{ Path = 'launchers\instalar.vbs'; Label = 'launchers\instalar.vbs' },
                @{ Path = 'launchers\iniciar.ps1'; Label = 'launchers\iniciar.ps1' },
                @{ Path = 'launchers\iniciar.vbs'; Label = 'launchers\iniciar.vbs' },
                @{ Path = 'launchers\update-core.ps1'; Label = 'motor de atualizacao' },
                @{ Path = 'launchers\apply-update.ps1'; Label = 'aplicacao de atualizacao preparada' },
                @{ Path = 'backend\neveai\__init__.py'; Label = 'pacote backend' },
                @{ Path = 'backend\neveai\main.py'; Label = 'backend main.py' },
                @{ Path = 'backend\neveai\routers\music_generation.py'; Label = 'geração musical' },
                @{ Path = 'backend\neveai\routers\video_generation.py'; Label = 'geração de vídeo' },
                @{ Path = 'backend\neveai\models\users.py'; Label = 'backend\neveai\models\users.py' },
                @{ Path = 'backend\neveai\models\models.py'; Label = 'backend\neveai\models\models.py' },
                @{ Path = 'backend\neveai\models\auths.py'; Label = 'backend\neveai\models\auths.py' },
                @{ Path = 'backend\neveai\routers\auths.py'; Label = 'backend\neveai\routers' },
                @{ Path = 'backend\neveai\utils\auth.py'; Label = 'backend\neveai\utils' },
                @{ Path = 'launchers\runtime-validation.ps1'; Label = 'launchers\runtime-validation.ps1' },
                @{ Path = 'launchers\process-ownership.ps1'; Label = 'launchers\process-ownership.ps1' },
                @{ Path = 'launchers\installer-release-cache.ps1'; Label = 'launchers\installer-release-cache.ps1' },
                @{ Path = 'desktop\runtime.json'; Label = 'WebView2 manifest' },
                @{ Path = 'desktop\setup_runtime.py'; Label = 'WebView2 setup' },
                @{ Path = 'desktop\NeveWindow.cs'; Label = 'WebView2 host' },
                @{ Path = 'desktop\app.manifest'; Label = 'WebView2 DPI manifest' },
                @{ Path = 'desktop\verify-runtime.ps1'; Label = 'WebView2 verification' },
                @{ Path = 'desktop\profile_migration.py'; Label = 'WebView2 profile migration' }
            )
            $missing = @()
            foreach ($item in $required) {
                $path = Join-Path $root $item.Path
                if (-not (Test-Path -LiteralPath $path)) { $missing += $item.Label }
            }
            [pscustomobject]@{ Ok = $missing.Count -eq 0; Missing = $missing }
        }

function Copy-ReleaseInstallerFiles([string]$sourceRoot, [string]$destinationRoot) {
            $relativeFiles = @(
                'instalar.bat',
                'launchers\instalar.ps1',
                'launchers\instalar.vbs',
                'launchers\iniciar.ps1',
                'launchers\iniciar.vbs'
            )
            foreach ($relativePath in $relativeFiles) {
                if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot $relativePath))) {
                    throw "Release do GitHub não contém $relativePath; atualização abortada antes de alterar os launchers atuais."
                }
            }

            $transactionRoot = Join-Path $env:TEMP "neve_launcher_tx_$([guid]::NewGuid().ToString('N'))"
            $backupRoot = Join-Path $transactionRoot 'backup'
            $stageRoot = Join-Path $transactionRoot 'stage'
            New-Item -ItemType Directory -Path $backupRoot,$stageRoot -Force | Out-Null
            $committed = @()
            try {
                foreach ($relativePath in $relativeFiles) {
                    $sourceFile = Join-Path $sourceRoot $relativePath
                    $destinationFile = Join-Path $destinationRoot $relativePath
                    $stageFile = Join-Path $stageRoot $relativePath
                    $backupFile = Join-Path $backupRoot $relativePath
                    New-Item -ItemType Directory -Path (Split-Path -Parent $stageFile) -Force | Out-Null
                    Copy-Item -LiteralPath $sourceFile -Destination $stageFile -Force -EA Stop
                    if (Test-Path -LiteralPath $destinationFile) {
                        New-Item -ItemType Directory -Path (Split-Path -Parent $backupFile) -Force | Out-Null
                        Copy-Item -LiteralPath $destinationFile -Destination $backupFile -Force -EA Stop
                    }
                }

                foreach ($relativePath in $relativeFiles) {
                    $stageFile = Join-Path $stageRoot $relativePath
                    $destinationFile = Join-Path $destinationRoot $relativePath
                    $destinationDir = Split-Path -Parent $destinationFile
                    New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
                    $pendingFile = "$destinationFile.neve-new-$([guid]::NewGuid().ToString('N'))"
                    Copy-Item -LiteralPath $stageFile -Destination $pendingFile -Force -EA Stop
                    try {
                        if (Test-Path -LiteralPath $destinationFile) {
                            try {
                                [System.IO.File]::Replace($pendingFile, $destinationFile, $null, $true)
                            } catch {
                                Move-Item -LiteralPath $pendingFile -Destination $destinationFile -Force -EA Stop
                            }
                        } else {
                            Move-Item -LiteralPath $pendingFile -Destination $destinationFile -Force -EA Stop
                        }
                    } finally {
                        Remove-Item -LiteralPath $pendingFile -Force -EA SilentlyContinue
                    }
                    $committed += $relativePath
                    L "[OK] $relativePath atualizado a partir do release do GitHub"
                }
            } catch {
                $commitError = $_
                foreach ($relativePath in $committed) {
                    $destinationFile = Join-Path $destinationRoot $relativePath
                    $backupFile = Join-Path $backupRoot $relativePath
                    try {
                        if (Test-Path -LiteralPath $backupFile) {
                            Copy-Item -LiteralPath $backupFile -Destination $destinationFile -Force -EA Stop
                        } else {
                            Remove-Item -LiteralPath $destinationFile -Force -EA SilentlyContinue
                        }
                    } catch {}
                }
                throw "Falha ao trocar os launchers; os anteriores foram restaurados: $($commitError.Exception.Message)"
            } finally {
                Remove-Item -LiteralPath $transactionRoot -Recurse -Force -EA SilentlyContinue
            }
        }

function Get-RelativePath([string]$basePath, [string]$path) {
            $baseFull = [System.IO.Path]::GetFullPath($basePath).TrimEnd('\', '/')
            $pathFull = [System.IO.Path]::GetFullPath($path)
            if ($pathFull.Length -le $baseFull.Length) { return '' }
            return $pathFull.Substring($baseFull.Length).TrimStart('\', '/')
        }

function Test-ReleaseExcluded([string]$relativePath, [bool]$isDirectory, [string[]]$excludeDirs, [string[]]$excludeFiles) {
            $normalized = ($relativePath -replace '/', '\').TrimStart('\')
            if ([string]::IsNullOrWhiteSpace($normalized)) { return $false }

            foreach ($dir in $excludeDirs) {
                $excludedDir = ($dir -replace '/', '\').Trim('\')
                if (
                    $normalized.Equals($excludedDir, [System.StringComparison]::OrdinalIgnoreCase) -or
                    $normalized.StartsWith($excludedDir + '\', [System.StringComparison]::OrdinalIgnoreCase)
                ) {
                    return $true
                }
            }

            if (-not $isDirectory) {
                $leaf = Split-Path -Path $normalized -Leaf
                foreach ($file in $excludeFiles) {
                    if ($leaf.Equals($file, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
                }
            }

            return $false
        }

function Test-ReleaseProtectedDescendant([string]$relativePath, [string]$directoryPath, [string[]]$excludeDirs, [string[]]$excludeFiles) {
            $normalized = ($relativePath -replace '/', '\').Trim('\')
            if ([string]::IsNullOrWhiteSpace($normalized)) { return $true }

            foreach ($dir in $excludeDirs) {
                $excludedDir = ($dir -replace '/', '\').Trim('\')
                if ($excludedDir.StartsWith($normalized + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
                    return $true
                }
            }

            foreach ($file in $excludeFiles) {
                try {
                    $match = Get-ChildItem -LiteralPath $directoryPath -Filter $file -File -Recurse -Force -EA SilentlyContinue | Select-Object -First 1
                    if ($match) { return $true }
                } catch {}
            }

            return $false
        }

function Remove-ReleaseItem([System.IO.FileSystemInfo]$item) {
            try {
                Remove-Item -LiteralPath $item.FullName -Recurse -Force -EA Stop
                $script:RemovedReleaseItems++
            } catch {
                throw "Falha ao remover item antigo '$($item.FullName)': $($_.Exception.Message)"
            }
        }

function Remove-ReleaseOrphans([string]$destinationPath, [string]$sourceRoot, [string]$destinationRoot, [string[]]$excludeDirs, [string[]]$excludeFiles) {
            if (-not (Test-Path -LiteralPath $destinationPath)) { return }

            $children = @(Get-ChildItem -LiteralPath $destinationPath -Force -EA SilentlyContinue)
            foreach ($child in $children) {
                $relativePath = Get-RelativePath $destinationRoot $child.FullName

                if (Test-ReleaseExcluded $relativePath $child.PSIsContainer $excludeDirs $excludeFiles) {
                    $script:SkippedReleaseItems++
                    continue
                }

                $sourcePath = Join-Path $sourceRoot $relativePath
                if (Test-Path -LiteralPath $sourcePath) {
                    $sourceItem = Get-Item -LiteralPath $sourcePath -Force
                    if ($child.PSIsContainer -and $sourceItem.PSIsContainer) {
                        Remove-ReleaseOrphans $child.FullName $sourceRoot $destinationRoot $excludeDirs $excludeFiles
                    } elseif ($child.PSIsContainer -ne $sourceItem.PSIsContainer) {
                        if ($child.PSIsContainer -and (Test-ReleaseProtectedDescendant $relativePath $child.FullName $excludeDirs $excludeFiles)) {
                            Remove-ReleaseOrphans $child.FullName $sourceRoot $destinationRoot $excludeDirs $excludeFiles
                        } else {
                            Remove-ReleaseItem $child
                        }
                    }
                    continue
                }

                if ($child.PSIsContainer -and (Test-ReleaseProtectedDescendant $relativePath $child.FullName $excludeDirs $excludeFiles)) {
                    Remove-ReleaseOrphans $child.FullName $sourceRoot $destinationRoot $excludeDirs $excludeFiles
                    continue
                }

                Remove-ReleaseItem $child
            }
        }

function Test-ReleaseFileContentEqual([string]$sourcePath, [string]$destinationPath) {
            if (-not (Test-Path -LiteralPath $destinationPath -PathType Leaf)) { return $false }

            $sourceStream = $null
            $destinationStream = $null
            try {
                $sourceStream = [System.IO.File]::Open(
                    $sourcePath,
                    [System.IO.FileMode]::Open,
                    [System.IO.FileAccess]::Read,
                    ([System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete)
                )
                $destinationStream = [System.IO.File]::Open(
                    $destinationPath,
                    [System.IO.FileMode]::Open,
                    [System.IO.FileAccess]::Read,
                    ([System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete)
                )
                if ($sourceStream.Length -ne $destinationStream.Length) { return $false }

                $sourceBuffer = New-Object byte[] 65536
                $destinationBuffer = New-Object byte[] 65536
                while ($true) {
                    $sourceRead = $sourceStream.Read($sourceBuffer, 0, $sourceBuffer.Length)
                    $destinationRead = $destinationStream.Read($destinationBuffer, 0, $destinationBuffer.Length)
                    if ($sourceRead -ne $destinationRead) { return $false }
                    if ($sourceRead -eq 0) { return $true }
                    for ($index = 0; $index -lt $sourceRead; $index++) {
                        if ($sourceBuffer[$index] -ne $destinationBuffer[$index]) { return $false }
                    }
                }
            } catch {
                return $false
            } finally {
                if ($destinationStream) { $destinationStream.Dispose() }
                if ($sourceStream) { $sourceStream.Dispose() }
            }
        }

function Copy-ReleaseFileRobust([string]$sourcePath, [string]$destinationPath, [int]$maxAttempts = 8) {
            for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
                try {
                    [System.IO.File]::Copy($sourcePath, $destinationPath, $true)
                    return $true
                } catch {
                    $copyError = $_.Exception
                    if (Test-ReleaseFileContentEqual $sourcePath $destinationPath) {
                        Write-UpdateLog "Arquivo em uso, mas já atualizado: $destinationPath"
                        return $false
                    }
                    if ($attempt -ge $maxAttempts) {
                        throw "Não foi possível substituir '$destinationPath' após $maxAttempts tentativas: $($copyError.Message)"
                    }

                    $delayMs = [Math]::Min(1500, 150 * [Math]::Pow(2, $attempt - 1))
                    Write-UpdateLog "Arquivo temporariamente indisponível; nova tentativa $($attempt + 1)/$maxAttempts em $delayMs ms: $destinationPath"
                    Start-Sleep -Milliseconds $delayMs
                }
            }
        }

function Copy-ReleaseTree([string]$sourcePath, [string]$sourceRoot, [string]$destinationRoot, [string[]]$excludeDirs, [string[]]$excludeFiles) {
            $item = Get-Item -LiteralPath $sourcePath -Force
            $relativePath = Get-RelativePath $sourceRoot $item.FullName

            if (Test-ReleaseExcluded $relativePath $item.PSIsContainer $excludeDirs $excludeFiles) {
                $script:SkippedReleaseItems++
                return
            }

            $destinationPath = Join-Path $destinationRoot $relativePath
            if ($item.PSIsContainer) {
                if (-not (Test-Path -LiteralPath $destinationPath)) {
                    [System.IO.Directory]::CreateDirectory($destinationPath) | Out-Null
                }
                Get-ChildItem -LiteralPath $item.FullName -Force | ForEach-Object {
                    Copy-ReleaseTree $_.FullName $sourceRoot $destinationRoot $excludeDirs $excludeFiles
                }
                return
            }

            $destinationParent = Split-Path -Parent $destinationPath
            if (-not (Test-Path -LiteralPath $destinationParent)) {
                [System.IO.Directory]::CreateDirectory($destinationParent) | Out-Null
            }
            if (Copy-ReleaseFileRobust $item.FullName $destinationPath) {
                $script:CopiedReleaseFiles++
            } else {
                $script:SkippedReleaseItems++
            }
        }

function Invoke-ReleaseDownload([string]$uri, [string]$destination) {
            if ($uri -notmatch '^https://api\.github\.com/repos/Etamus/NeveAI/zipball/') {
                throw 'URL de origem da release inesperada; atualização cancelada.'
            }
            $tagPath = [uri]::EscapeDataString($latestTag)
            $sources = @(
                $uri,
                "https://github.com/Etamus/NeveAI/archive/refs/tags/$tagPath.zip",
                "https://codeload.github.com/Etamus/NeveAI/zip/refs/tags/$tagPath"
            ) | Select-Object -Unique
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            $failures = @()
            foreach ($source in $sources) {
                $headers = @{ 'User-Agent' = 'Neve-Updater/2.0' }
                if ($source -like 'https://api.github.com/*') { $headers['Accept'] = 'application/vnd.github+json' }
                for ($attempt = 1; $attempt -le 3; $attempt++) {
                    try {
                        Remove-Item -LiteralPath $destination -Force -EA SilentlyContinue
                        Invoke-WebRequest $source -OutFile $destination -UseBasicParsing -Headers $headers -TimeoutSec 600 -EA Stop
                        if (-not (Test-Path -LiteralPath $destination)) { throw 'O download não criou o arquivo esperado.' }
                        if ((Get-Item -LiteralPath $destination).Length -lt 1KB) { throw 'O pacote baixado está vazio ou incompleto.' }
                        $archive = [System.IO.Compression.ZipFile]::OpenRead($destination)
                        try { if ($archive.Entries.Count -eq 0) { throw 'O ZIP da release não contém arquivos.' } }
                        finally { $archive.Dispose() }
                        L "[OK] ZIP validado: $source"
                        return
                    } catch {
                        $errorMessage = $_.Exception.Message
                        $failures += "$source (tentativa $attempt): $errorMessage"
                        Remove-Item -LiteralPath $destination -Force -EA SilentlyContinue
                        $status = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 }
                        if ($status -in @(400, 401, 403, 404, 415)) {
                            L "[!] Fonte recusou o download (HTTP $status); tentando outra origem." 'warn'
                            break
                        }
                        if ($attempt -lt 3) {
                            L "[!] Download falhou na tentativa $attempt/3: $errorMessage. Tentando novamente..." 'warn'
                            Start-Sleep -Seconds ([math]::Min(8, [math]::Pow(2, $attempt)))
                        }
                    }
                }
            }
            throw "Não foi possível baixar um ZIP válido da release $latestTag. Última falha: $($failures[-1])"
        }

function New-ReleaseRollbackSnapshot([string]$sourceRoot, [string]$snapshotRoot, [string[]]$excludeDirs, [string[]]$excludeFiles) {
            New-Item -ItemType Directory -Path $snapshotRoot -Force | Out-Null
            $savedCopied = $script:CopiedReleaseFiles
            $savedSkipped = $script:SkippedReleaseItems
            try {
                foreach ($item in @(Get-ChildItem -LiteralPath $sourceRoot -Force -EA Stop)) {
                    Copy-ReleaseTree $item.FullName $sourceRoot $snapshotRoot $excludeDirs $excludeFiles
                }
            } finally {
                $script:CopiedReleaseFiles = $savedCopied
                $script:SkippedReleaseItems = $savedSkipped
            }
        }

function Restore-ReleaseRollbackSnapshot([string]$snapshotRoot, [string]$destinationRoot, [string[]]$excludeDirs, [string[]]$excludeFiles) {
            if (-not (Test-Path -LiteralPath $snapshotRoot)) { throw 'Snapshot de restauração não encontrado.' }
            $savedCopied = $script:CopiedReleaseFiles
            $savedRemoved = $script:RemovedReleaseItems
            $savedSkipped = $script:SkippedReleaseItems
            try {
                Remove-ReleaseOrphans $destinationRoot $snapshotRoot $destinationRoot $excludeDirs $excludeFiles
                foreach ($item in @(Get-ChildItem -LiteralPath $snapshotRoot -Force -EA Stop)) {
                    Copy-ReleaseTree $item.FullName $snapshotRoot $destinationRoot $excludeDirs $excludeFiles
                }
            } finally {
                $script:CopiedReleaseFiles = $savedCopied
                $script:RemovedReleaseItems = $savedRemoved
                $script:SkippedReleaseItems = $savedSkipped
            }
        }

function Publish-FrontendAtomically([string]$sourceDir, [string]$destinationDir) {
            if (-not (Test-Path -LiteralPath (Join-Path $sourceDir 'index.html'))) {
                throw 'O build novo não contém index.html; o frontend atual foi mantido.'
            }
            $parent = Split-Path -Parent $destinationDir
            $suffix = [guid]::NewGuid().ToString('N')
            $stagedDir = Join-Path $parent "frontend.neve-new-$suffix"
            $backupDir = Join-Path $parent "frontend.neve-old-$suffix"
            $hadExisting = Test-Path -LiteralPath $destinationDir
            New-Item -ItemType Directory -Path $stagedDir -Force | Out-Null
            try {
                Get-ChildItem -LiteralPath $sourceDir -Force | Copy-Item -Destination $stagedDir -Recurse -Force -EA Stop
                if ($hadExisting) {
                    Move-Item -LiteralPath $destinationDir -Destination $backupDir -Force -EA Stop
                }
                try {
                    Move-Item -LiteralPath $stagedDir -Destination $destinationDir -Force -EA Stop
                } catch {
                    if (Test-Path -LiteralPath $backupDir) {
                        Move-Item -LiteralPath $backupDir -Destination $destinationDir -Force -EA SilentlyContinue
                    }
                    throw
                }
                return [pscustomobject]@{
                    Destination = $destinationDir
                    Backup      = if ($hadExisting) { $backupDir } else { $null }
                    HadExisting = $hadExisting
                }
            } finally {
                Remove-Item -LiteralPath $stagedDir -Recurse -Force -EA SilentlyContinue
                if ((Test-Path -LiteralPath $backupDir) -and -not (Test-Path -LiteralPath $destinationDir)) {
                    Move-Item -LiteralPath $backupDir -Destination $destinationDir -Force -EA SilentlyContinue
                }
            }
        }

function Test-NeveInstallState([string]$root) {
            $required = @(
                @{ Path = '.env'; Label = '.env' },
                @{ Path = 'backend\neveai\venv\Scripts\python.exe'; Label = 'venv Python' },
                @{ Path = 'backend\neveai\venv\pyvenv.cfg'; Label = 'venv configuration' }
            )
            $missing = @()
            foreach ($item in $required) {
                $path = Join-Path $root $item.Path
                if (-not (Test-Path -LiteralPath $path)) { $missing += $item.Label }
            }

            [pscustomobject]@{
                Installed = $missing.Count -eq 0
                Missing   = $missing
            }
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
                    return New-LlamaTarget 'NVIDIA' $name 'NVIDIA CUDA 13' @('cuda-13.4','cuda-cu13.4','cuda-13.3','cuda-cu13.3') "GPU NVIDIA Blackwell detectada: $name."
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
                $gpus = Get-CimInstance Win32_VideoController -EA SilentlyContinue
                $amdGpu = $gpus | Where-Object { $_.Name -match 'AMD|Radeon|RX\s' } |
                    Sort-Object @{ Expression = { if ($_.Name -match '\bRX\s*\d|Radeon\s+Pro\b') { 0 } elseif ($_.Name -match 'Vega\s*\d+\s*Graphics|Radeon(?:\(TM\))?\s+Graphics') { 2 } else { 1 } } },
                                @{ Expression = { [long]$_.AdapterRAM }; Descending = $true } | Select-Object -First 1
                if ($amdGpu) { return New-LlamaTarget 'AMD' $amdGpu.Name.Trim() 'AMD Vulkan' @('vulkan') "GPU AMD detectada: $($amdGpu.Name.Trim())." }
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
            foreach ($asset in @($assets)) {
                $assetMatch = [regex]::Match([string]$asset.name, '^llama-.+-bin-win-(.+)-x64\.zip$')
                if (-not $assetMatch.Success) { continue }
                foreach ($backend in $backends) {
                    if (Test-LlamaBackendCompatible $backend $assetMatch.Groups[1].Value) { return $asset }
                }
            }
            foreach ($backend in $backends) {
                $asset = New-LlamaReleaseAsset $tag "llama-$tag-bin-win-$backend-x64.zip"
                if (Test-ReleaseAssetUrl $asset.browser_download_url) { return $asset }
            }
            return $null
        }

function Find-CudaRuntimeAsset($assets, [string]$tag, [string[]]$backends) {
            foreach ($backend in $backends) {
                $backendEsc = [regex]::Escape($backend)
                $match = $assets | Where-Object { $_.name -match "^cudart-llama-bin-win-$backendEsc-x64\.zip$" } | Select-Object -First 1
                if ($match) { return $match }
            }
            foreach ($asset in @($assets)) {
                $assetMatch = [regex]::Match([string]$asset.name, '^cudart-llama-bin-win-(.+)-x64\.zip$')
                if (-not $assetMatch.Success) { continue }
                foreach ($backend in $backends) {
                    if (Test-LlamaBackendCompatible $backend $assetMatch.Groups[1].Value) { return $asset }
                }
            }
            foreach ($backend in $backends) {
                $asset = New-LlamaReleaseAsset $tag "cudart-llama-bin-win-$backend-x64.zip"
                if (Test-ReleaseAssetUrl $asset.browser_download_url) { return $asset }
            }
            return $null
        }

function Update-NeveAI {
            Set-Location -LiteralPath $ROOT
            if (-not $latestTag -or -not $zipUrl) { throw 'Release do NeveAI indisponível para atualização.' }
            $installState = Test-NeveInstallState $ROOT
            $canBuildAndDeploy = [bool]$installState.Installed
            if (-not $canBuildAndDeploy) {
                L "[!] Instalação incompleta detectada. Build/deploy serão pulados." 'warn'
                L "    Faltando: $($installState.Missing -join ', ')" 'warn'
                L "    Rode instalar.bat para concluir a instalação antes de gerar frontend." 'warn'
            }

            $operationId = [guid]::NewGuid().ToString('N')
            $tmpZip = Join-Path $env:TEMP "neve_update_$operationId.zip"
            $tmpExt = Join-Path $env:TEMP "neve_update_ext_$operationId"
            $rollbackRoot = Join-Path $env:TEMP "neve_update_rollback_$operationId"
            $envFile = Join-Path $ROOT '.env'
            $envBackup = $null
            $mutationStarted = $false
            $frontendTransaction = $null
            $backendDependenciesChanged = $false
            $rollbackRequirement = $null
            $preserveRollback = $false
            $versionExisted = Test-Path -LiteralPath $VERSION_FILE
            $previousVersion = if ($versionExisted) { Get-Content -LiteralPath $VERSION_FILE -Raw -EA SilentlyContinue } else { $null }
            $excludeDirs = @('backend\neveai\venv','backend\neveai\frontend','backend\neveai\data','backend\data','backend\__pycache__','models','mmproj','llamacpp-server','node_modules','build','logs','tools\nodejs','.desktop','.git','.vscode','.svelte-kit')
            $excludeFiles = @('.env', 'version.txt', 'instalar.bat', 'instalar.ps1', 'instalar.vbs', 'iniciar.ps1', 'iniciar.vbs')

            try {
                PN 5 "Baixando NeveAI $latestTag"
                L "==> Download $zipUrl"
                Invoke-ReleaseDownload $zipUrl $tmpZip
                $sizeMB = [math]::Round((Get-Item -LiteralPath $tmpZip).Length / 1MB, 1)
                L "[OK] NeveAI baixado ($sizeMB MB)"

                PN 18 'Extraindo e validando NeveAI'
                New-Item $tmpExt -ItemType Directory -Force | Out-Null
                Expand-Archive $tmpZip -DestinationPath $tmpExt -Force -EA Stop
                $inner = Get-ChildItem -LiteralPath $tmpExt -Directory | Select-Object -First 1
                if (-not $inner) { throw 'Estrutura inesperada do zip da release.' }
                $sourceRoot = (Resolve-Path -LiteralPath $inner.FullName).ProviderPath
                $destinationRoot = (Resolve-Path -LiteralPath $ROOT).ProviderPath
                if ($sourceRoot.Equals($destinationRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
                    throw 'A pasta fonte da release é igual à pasta de instalação; atualização abortada.'
                }
                $releaseIntegrity = Test-NeveAppIntegrity $sourceRoot
                if (-not $releaseIntegrity.Ok) {
                    throw "Release incompleta; nenhum arquivo local foi alterado. Faltando: $($releaseIntegrity.Missing -join ', ')."
                }
                L "[OK] Pasta da instalação: $destinationRoot"
                L "[OK] Pasta da release validada: $sourceRoot"

                PN 27 'Preservando dados e estado atual'
                if (Test-Path -LiteralPath $envFile) {
                    $envBackup = Join-Path $env:TEMP "neve_update_env_$operationId.bak"
                    Copy-Item -LiteralPath $envFile -Destination $envBackup -Force -EA Stop
                    L '[OK] .env preservado'
                }
                New-ReleaseRollbackSnapshot $destinationRoot $rollbackRoot $excludeDirs $excludeFiles
                $desktopState = Join-Path $ROOT '.desktop\installed.json'
                if (Test-Path -LiteralPath $desktopState) {
                    $desktopBackupFolder = Join-Path $rollbackRoot '.desktop'
                    New-Item -ItemType Directory -Force -Path $desktopBackupFolder | Out-Null
                    Copy-Item -LiteralPath $desktopState -Destination (Join-Path $desktopBackupFolder 'installed.json') -Force
                }
                L '[OK] Ponto de restauração criado'

                PN 38 'Aplicando arquivos do NeveAI'
                $mutationStarted = $true
                $script:CopiedReleaseFiles = 0
                $script:RemovedReleaseItems = 0
                $script:SkippedReleaseItems = 0
                Remove-ReleaseOrphans $destinationRoot $sourceRoot $destinationRoot $excludeDirs $excludeFiles
                foreach ($item in @(Get-ChildItem -LiteralPath $sourceRoot -Force -EA Stop)) {
                    Copy-ReleaseTree $item.FullName $sourceRoot $destinationRoot $excludeDirs $excludeFiles
                }
                L "[OK] Arquivos de release aplicados ($script:CopiedReleaseFiles arquivos, $script:RemovedReleaseItems órfãos removidos, $script:SkippedReleaseItems itens preservados)"

                $integrity = Test-NeveAppIntegrity $ROOT
                if (-not $integrity.Ok) {
                    throw "Release aplicada sem arquivos essenciais: $($integrity.Missing -join ', ')."
                }
                if ($envBackup -and -not (Test-Path -LiteralPath $envFile)) {
                    Copy-Item -LiteralPath $envBackup -Destination $envFile -Force -EA Stop
                }
                L '[OK] Integridade dos arquivos essenciais validada'

                if (Test-Path -LiteralPath (Join-Path $ROOT 'backend\neveai\venv\Scripts\python.exe')) {
                    PN 46 'Atualizando janela WebView2 Fixed'
                    $desktopSetup = Join-Path $ROOT 'desktop\setup_runtime.py'
                    $desktopPython = Join-Path $ROOT 'backend\neveai\venv\Scripts\python.exe'
                    $rc = Run $desktopPython @($desktopSetup) 'WebView2 Fixed e janela nativa' 1800
                    if ($rc -ne 0) { throw "Falha ao atualizar WebView2 Fixed (codigo $rc)." }
                }

                if ($canBuildAndDeploy) {
                    $requirementRelative = if (Test-Path -LiteralPath (Join-Path $ROOT 'backend\requirements-runtime.txt')) { 'backend\requirements-runtime.txt' } else { 'backend\requirements.txt' }
                    $activeRequirement = Join-Path $ROOT $requirementRelative
                    $rollbackRequirement = Join-Path $rollbackRoot $requirementRelative
                    if (-not (Test-Path -LiteralPath $activeRequirement)) { throw 'A release não contém a lista de dependências do backend.' }
                    $backendDependenciesChanged = -not (Test-Path -LiteralPath $rollbackRequirement)
                    if (-not $backendDependenciesChanged) {
                        $backendDependenciesChanged = (Get-FileHash -LiteralPath $activeRequirement -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $rollbackRequirement -Algorithm SHA256).Hash
                    }
                    if ($backendDependenciesChanged) {
                        PN 48 'Atualizando dependências do backend'
                        $venvPython = Join-Path $ROOT 'backend\neveai\venv\Scripts\python.exe'
                        if (-not (Test-Path -LiteralPath $venvPython)) { throw 'Python do ambiente virtual não encontrado para atualizar as dependências do backend.' }
                        $rc = Run $venvPython @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', $activeRequirement) 'dependências do backend' 3600
                        if ($rc -ne 0) { throw "Atualização das dependências do backend falhou (código $rc)" }
                        L '[OK] Dependências do backend sincronizadas'
                    }
                }

                if ($canBuildAndDeploy) {
                    PN 55 'Instalando dependências do frontend'
                    $frontendNode = Resolve-FrontendNodeLaunch
                    if (-not $frontendNode) { $frontendNode = Install-PortableNode22 }
                    if (-not $frontendNode) { throw 'Node.js 18-22 com npm não encontrado e o Node.js 22 portátil não pôde ser preparado.' }
                    $script:FrontendNodeDir = $frontendNode.NodeDir
                    $npmExe = $frontendNode.NpmExecutable
                    L "[OK] Node.js do frontend: $($frontendNode.NodeVersion) / npm $($frontendNode.NpmVersion) em $($frontendNode.NodeDir)"
                    $rc = Run $npmExe @('install', '--no-audit', '--no-fund', '--prefer-offline') 'npm install' 2700
                    if ($rc -ne 0) {
                        L '[!] npm install falhou; tentando novamente com preferência pela rede.' 'warn'
                        $rc = Run $npmExe @('install', '--no-audit', '--no-fund', '--prefer-online') 'npm install de recuperação' 2700
                    }
                    if ($rc -ne 0) { throw "npm install falhou após duas tentativas (código $rc)" }

                    $previousOfficeCliSkipUpdate = $env:OFFICECLI_SKIP_UPDATE
                    $previousOfficeCliNoAutoResident = $env:OFFICECLI_NO_AUTO_RESIDENT
                    try {
                        $env:OFFICECLI_SKIP_UPDATE = '1'
                        $env:OFFICECLI_NO_AUTO_RESIDENT = '1'
                        $officeCli = Join-Path $ROOT 'node_modules\@officecli\officecli\vendor\officecli.exe'
                        if (-not (Test-Path -LiteralPath $officeCli)) {
                            $rc = Run $npmExe @('exec', '--', 'officecli', '--version') 'preparar OfficeCLI'
                            if ($rc -ne 0 -or -not (Test-Path -LiteralPath $officeCli)) {
                                throw 'Falha ao preparar o OfficeCLI para geração de DOCX, XLSX e PPTX.'
                            }
                        }
                        $rc = Run $officeCli @('--version') 'validar OfficeCLI'
                        if ($rc -ne 0) { throw "OfficeCLI instalado, mas a validação falhou (código $rc)." }
                    } finally {
                        if ($null -eq $previousOfficeCliSkipUpdate) { Remove-Item Env:\OFFICECLI_SKIP_UPDATE -ErrorAction SilentlyContinue } else { $env:OFFICECLI_SKIP_UPDATE = $previousOfficeCliSkipUpdate }
                        if ($null -eq $previousOfficeCliNoAutoResident) { Remove-Item Env:\OFFICECLI_NO_AUTO_RESIDENT -ErrorAction SilentlyContinue } else { $env:OFFICECLI_NO_AUTO_RESIDENT = $previousOfficeCliNoAutoResident }
                    }
                    L '[OK] OfficeCLI pronto para gerar DOCX, XLSX e PPTX'

                    PN 76 'Gerando build do frontend'
                    Remove-Item -LiteralPath (Join-Path $ROOT 'build') -Recurse -Force -EA SilentlyContinue
                    $rc = Run $npmExe @('run', 'build', '--', '--logLevel', 'error') 'npm run build' 1800
                    if ($rc -ne 0) {
                        L '[!] O build falhou; tentando novamente após liberar os arquivos.' 'warn'
                        Start-Sleep -Seconds 3
                        $rc = Run $npmExe @('run', 'build', '--', '--logLevel', 'error') 'npm run build novamente' 1800
                    }
                    if ($rc -ne 0) {
                        L '[!] O build falhou duas vezes; reparando as dependências npm antes da última tentativa.' 'warn'
                        $npmRc = Run $npmExe @('install', '--no-audit', '--no-fund', '--prefer-online') 'npm install de recuperação do build' 2700
                        if ($npmRc -ne 0) { throw "Build falhou e npm install de recuperação também falhou (código $npmRc)." }
                        if (-not (Test-Path -LiteralPath $officeCli)) {
                            $officeRc = Run $npmExe @('exec', '--', 'officecli', '--version') 'preparar OfficeCLI após recuperação npm' 600
                            if ($officeRc -ne 0 -or -not (Test-Path -LiteralPath $officeCli)) { throw 'OfficeCLI ausente após recuperação npm.' }
                        }
                        $rc = Run $npmExe @('run', 'build', '--', '--logLevel', 'error') 'npm run build após recuperação npm' 1800
                    }
                    if ($rc -ne 0) { throw "npm run build falhou após recuperação (código $rc). Consulte logs\update.log." }

                    PN 91 'Publicando frontend'
                    $buildDir = Join-Path $ROOT 'build'
                    $deployDir = Join-Path $ROOT 'backend\neveai\frontend'
                    $frontendTransaction = Publish-FrontendAtomically $buildDir $deployDir
                    L '[OK] Frontend novo publicado de forma transacional'
                } else {
                    PN 91 'Pulando build/deploy'
                    L '[OK] Build e deploy pulados porque o projeto ainda não foi instalado.'
                }

                PN 96 'Finalizando atualização'
                if ($canBuildAndDeploy) {
                    $validator = Join-Path $ROOT 'launchers\runtime-validation.ps1'
                    $rc = Run (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') @('-NoProfile','-ExecutionPolicy','Bypass','-File',$validator,'-Root',$ROOT,'-Check') 'validar inicializacao apos atualizacao' 60
                    if ($rc -ne 0) { throw 'A atualizacao nao passou na validacao de inicializacao; restaurando a versao anterior.' }
                }
                [System.IO.File]::WriteAllText($VERSION_FILE, $latestTag, [System.Text.UTF8Encoding]::new($false))
                Copy-ReleaseInstallerFiles $sourceRoot $destinationRoot
                $mutationStarted = $false
                if ($frontendTransaction -and $frontendTransaction.Backup) {
                    Remove-Item -LiteralPath $frontendTransaction.Backup -Recurse -Force -EA SilentlyContinue
                }
                try { L "[OK] NeveAI atualizado para $latestTag" } catch {}
                if ($canBuildAndDeploy) { return "NeveAI: $currentVersion -> $latestTag" }
                return "NeveAI: $currentVersion -> $latestTag (build/deploy pulados; instalação incompleta)"
            } catch {
                $updateError = $_
                if ($mutationStarted) {
                    L '[!] A atualização não foi concluída; restaurando a instalação anterior...' 'warn'
                    try {
                        if ($frontendTransaction) {
                            Remove-Item -LiteralPath $frontendTransaction.Destination -Recurse -Force -EA SilentlyContinue
                            if ($frontendTransaction.HadExisting -and (Test-Path -LiteralPath $frontendTransaction.Backup)) {
                                Move-Item -LiteralPath $frontendTransaction.Backup -Destination $frontendTransaction.Destination -Force -EA Stop
                            }
                        }
                        Restore-ReleaseRollbackSnapshot $rollbackRoot $ROOT $excludeDirs $excludeFiles
                        $desktopStateBackup = Join-Path $rollbackRoot '.desktop\installed.json'
                        if (Test-Path -LiteralPath $desktopStateBackup) {
                            Copy-Item -LiteralPath $desktopStateBackup -Destination (Join-Path $ROOT '.desktop\installed.json') -Force
                        }
                        if ($backendDependenciesChanged -and $rollbackRequirement -and (Test-Path -LiteralPath $rollbackRequirement)) {
                            $venvPython = Join-Path $ROOT 'backend\neveai\venv\Scripts\python.exe'
                            if (Test-Path -LiteralPath $venvPython) {
                                $restoreRc = Run $venvPython @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', $rollbackRequirement) 'restauração das dependências do backend' 3600
                                if ($restoreRc -ne 0) { L '[!] Não foi possível ressincronizar todas as dependências antigas; os arquivos do projeto foram restaurados.' 'warn' }
                            }
                        }
                        if ($envBackup -and (Test-Path -LiteralPath $envBackup)) {
                            Copy-Item -LiteralPath $envBackup -Destination $envFile -Force -EA Stop
                        }
                        if ($versionExisted) {
                            [System.IO.File]::WriteAllText($VERSION_FILE, [string]$previousVersion, [System.Text.UTF8Encoding]::new($false))
                        } else {
                            Remove-Item -LiteralPath $VERSION_FILE -Force -EA SilentlyContinue
                        }
                        L '[OK] Instalação anterior restaurada.'
                    } catch {
                        $preserveRollback = $true
                        [IO.File]::WriteAllText((Join-Path $ROOT 'logs\install-state.txt'), 'failed', [Text.UTF8Encoding]::new($false))
                        throw "A atualização falhou e a restauração automática também encontrou um erro: $($_.Exception.Message). Backup preservado em $rollbackRoot. Erro original: $($updateError.Exception.Message)"
                    }
                }
                throw $updateError
            } finally {
                Remove-Item -LiteralPath $tmpZip -Force -EA SilentlyContinue
                Remove-Item -LiteralPath $tmpExt -Recurse -Force -EA SilentlyContinue
                if (-not $preserveRollback) {
                    Remove-Item -LiteralPath $rollbackRoot -Recurse -Force -EA SilentlyContinue
                    if ($envBackup) { Remove-Item -LiteralPath $envBackup -Force -EA SilentlyContinue }
                }
            }
        }

function Update-LlamaCpp {
            $tmpFiles = @(); $stageDir = $null; $backupDir = $null
            try {
                PL 5 'Detectando hardware para llama.cpp'
                $target = Get-LlamaHardwareTarget
                L "[OK] Alvo llama.cpp: $($target.Label)"
                if ($target.Name) { L "    Hardware: $($target.Name)" }

                PL 10 'Consultando releases do llama.cpp'
                $rel = Get-LatestLlamaRelease ([string[]]$target.Backends)
                $tag = $rel.tag_name
                if (-not $tag) { throw 'Release do llama.cpp sem tag_name.' }
                $installed = Get-InstalledLlamaInfo $ROOT
                if ($installed.Tag -and $installed.Tag -eq $tag) {
                    L "[OK] llama.cpp já está na última release ($tag). Nenhum download necessário."
                    return "llama.cpp: já atualizado ($tag)"
                }

                $mainAsset = Find-LlamaBinAsset $rel.assets $tag ([string[]]$target.Backends)
                if (-not $mainAsset) { throw "O release $tag não contém um asset Windows x64 para $($target.Label). Nada foi instalado." }
                $isCuda = (@($target.Backends) | Where-Object { $_ -match '^cuda' } | Select-Object -First 1) -ne $null
                $runtimeAsset = $null
                if ($isCuda) { $runtimeAsset = Find-CudaRuntimeAsset $rel.assets $tag ([string[]]$target.Backends) }

                PL 28 'Baixando llama.cpp'
                $tmpMain = Join-Path $env:TEMP "neve_llama_$([guid]::NewGuid().ToString('N')).zip"
                $tmpFiles += $tmpMain
                Invoke-ReleaseDownload $mainAsset.browser_download_url $tmpMain
                $tmpRuntime = $null
                if ($runtimeAsset) {
                    $tmpRuntime = Join-Path $env:TEMP "neve_llama_cudart_$([guid]::NewGuid().ToString('N')).zip"
                    $tmpFiles += $tmpRuntime
                    Invoke-ReleaseDownload $runtimeAsset.browser_download_url $tmpRuntime
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
                    $expectedServer = [IO.Path]::GetFullPath((Join-Path $llamaDir 'llama-server.exe'))
                    Get-CimInstance Win32_Process -Filter "Name='llama-server.exe'" -EA SilentlyContinue | Where-Object {
                        $_.ExecutablePath -and [IO.Path]::GetFullPath($_.ExecutablePath) -eq $expectedServer
                    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue }
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
