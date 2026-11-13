$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$testRoot = Join-Path $repo ('logs\installer-regressions-' + [guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($testRoot)
$results = [Collections.Generic.List[string]]::new()
function Assert-Test([bool]$Condition, [string]$Name) { if (-not $Condition) { throw $Name }; $results.Add($Name) }
function Write-Fixture([string]$Path, [string]$Value = 'fixture') {
    [void][IO.Directory]::CreateDirectory((Split-Path $Path))
    [IO.File]::WriteAllText($Path, $Value, [Text.UTF8Encoding]::new($false))
}
function Parse-TestSource([string]$Text) {
    $tokens=$null; $errors=$null
    $ast=[Management.Automation.Language.Parser]::ParseInput($Text,[ref]$tokens,[ref]$errors)
    if ($errors.Count) { throw ($errors | Out-String) }
    return $ast
}

try {
    $source = [IO.File]::ReadAllText((Join-Path $repo 'launchers\instalar.ps1'))
    $ast = Parse-TestSource $source
    $updateAst = Parse-TestSource ([IO.File]::ReadAllText((Join-Path $repo 'launchers/update-core.ps1')))
    . (Join-Path $repo 'launchers/update-core.ps1')
    . (Join-Path $repo 'launchers\runtime-validation.ps1')
    . (Join-Path $repo 'launchers\process-ownership.ps1')
    . (Join-Path $repo 'launchers\installer-release-cache.ps1')
    function L { param($Message,$Kind) }
    function PN { param($Percent,$Phase) }
    function Write-UpdateLog { param($Message) }
    function Test-UpdateCancelled {}
    function Start-Sleep { param($Seconds,$Milliseconds) }

    $healthRoot = Join-Path $testRoot 'health'
    foreach ($path in @('.env','llamacpp-server\bin\llama-server.exe','backend\neveai\frontend\index.html','backend\neveai\models\users.py','neve_window.py','.desktop\installed.json')) { Write-Fixture (Join-Path $healthRoot $path) }
    Write-Fixture (Join-Path $healthRoot 'desktop\setup_runtime.py') 'import sys; sys.exit(0)'
    $python = Join-Path $healthRoot 'backend\neveai\venv\Scripts\python.exe'
    [void][IO.Directory]::CreateDirectory((Split-Path $python))
    Copy-Item -LiteralPath (Join-Path $repo 'backend\neveai\venv\Scripts\python.exe') -Destination $python
    Copy-Item -LiteralPath (Join-Path $repo 'backend\neveai\venv\pyvenv.cfg') -Destination (Join-Path $healthRoot 'backend\neveai\venv\pyvenv.cfg')
    Assert-Test (Get-NeveRuntimeHealth $healthRoot).Ok 'complete runtime passes without Node/OfficeCLI'
    $marker = Join-Path $healthRoot '.desktop\installed.json'
    Remove-Item -LiteralPath $marker
    Assert-Test (-not (Get-NeveRuntimeHealth $healthRoot).Ok) 'missing desktop state fails readiness'
    Write-Fixture $marker
    Write-Fixture (Join-Path $healthRoot 'desktop\setup_runtime.py') 'import sys; sys.exit(1)'
    Assert-Test (-not (Get-NeveRuntimeHealth $healthRoot).Ok) 'stale desktop host fails readiness'
    Write-Fixture (Join-Path $healthRoot 'desktop\setup_runtime.py') 'import sys; sys.exit(0)'
    Write-Fixture (Join-Path $healthRoot 'backend\neveai\frontend\index.html') '<script>import("./_app/start.js")</script>'
    Assert-Test (-not (Get-NeveRuntimeHealth $healthRoot).Ok) 'missing frontend entry asset fails readiness'
    Write-Fixture (Join-Path $healthRoot 'backend\neveai\frontend\_app\start.js') 'export{}'
    Assert-Test (Get-NeveRuntimeHealth $healthRoot).Ok 'complete frontend entry assets pass readiness'
    Write-Fixture (Join-Path $healthRoot 'desktop\setup_runtime.py') 'import time; time.sleep(60)'
    $probeTime=[Diagnostics.Stopwatch]::StartNew()
    Assert-Test (-not (Get-NeveRuntimeHealth $healthRoot -TimeoutMs 200).Ok) 'hung runtime validation fails instead of waiting indefinitely'
    Assert-Test ($probeTime.Elapsed.TotalSeconds -lt 4) 'runtime validation timeout is bounded'
    Write-Fixture (Join-Path $healthRoot 'desktop\setup_runtime.py') 'import sys; sys.exit(0)'

    $processes = @(
        @{ProcessId=10;ParentProcessId=1;Name='powershell.exe';CommandLine='installer';ExecutablePath='C:\Windows\powershell.exe'},
        @{ProcessId=11;ParentProcessId=10;Name='python.exe';CommandLine="$repo\backend\neveai\venv\Scripts\python.exe -c validation";ExecutablePath="$repo\backend\neveai\venv\Scripts\python.exe"},
        @{ProcessId=12;ParentProcessId=11;Name='python.exe';CommandLine='python -c validation';ExecutablePath='C:\Python\python.exe'},
        @{ProcessId=20;ParentProcessId=1;Name='llama-server.exe';CommandLine="$repo\llamacpp-server\bin\llama-server.exe";ExecutablePath="$repo\llamacpp-server\bin\llama-server.exe"},
        @{ProcessId=21;ParentProcessId=1;Name='python.exe';CommandLine='python -m uvicorn neveai.main:app';ExecutablePath="$repo\backend\neveai\venv\Scripts\python.exe"},
        @{ProcessId=22;ParentProcessId=1;Name='NeveAI.Window.exe';CommandLine='window';ExecutablePath="$repo\.desktop\host\NeveAI.Window.exe"},
        @{ProcessId=23;ParentProcessId=21;Name='python.exe';CommandLine='python -m uvicorn neveai.main:app';ExecutablePath='C:\Python\python.exe'},
        @{ProcessId=30;ParentProcessId=1;Name='llama-server.exe';CommandLine='C:\Other\llama-server.exe';ExecutablePath='C:\Other\llama-server.exe'},
        @{ProcessId=31;ParentProcessId=1;Name='python.exe';CommandLine='python -m uvicorn neveai.main:app';ExecutablePath='C:\Other\python.exe'}
    ) | ForEach-Object { [pscustomobject]$_ }
    Assert-Test ((@(Get-NeveProjectProcessIds $repo 10 $processes) -join ',') -eq '20,21,22,23') 'process ownership protects installer workers and other projects while recognizing venv child processes'

    $ROOT = Join-Path $testRoot 'cache'
    Save-InstallerCachedRelease 'neve' ([pscustomobject]@{tag_name='v1.2.3';body='fixture'})
    Assert-Test ((Get-InstallerCachedRelease 'neve').tag_name -eq 'v1.2.3') 'fresh project release cache works'
    Save-InstallerCachedRelease 'llama:cpu' ([pscustomobject]@{tag_name='b12345';assets=@()})
    Assert-Test ((Get-InstallerCachedRelease 'llama:cpu').tag_name -eq 'b12345') 'llama build tags are cached independently'
    Assert-Test ($null -eq (Get-InstallerCachedRelease 'llama:cuda')) 'release cache is backend-specific'
    $cachePath = Get-InstallerReleaseCachePath 'neve'
    Write-Fixture $cachePath '{broken'
    Assert-Test ($null -eq (Get-InstallerCachedRelease 'neve')) 'corrupt release cache is ignored'
    Write-Fixture $cachePath ((@{key='neve';saved=[DateTime]::UtcNow.AddMinutes(-2).ToString('o');release=@{tag_name='v1.2.3'}}) | ConvertTo-Json -Depth 5)
    Assert-Test ($null -eq (Get-InstallerCachedRelease 'neve')) 'stale release cache is ignored'
    Remove-Item -LiteralPath $cachePath
    $releaseSource = Join-Path $testRoot 'release\NeveAI'
    $integrityFunction = @($updateAst.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Test-NeveAppIntegrity'},$true))[-1]
    foreach ($match in [regex]::Matches($integrityFunction.Extent.Text, "Path = '([^']+)'")) { Write-Fixture (Join-Path $releaseSource $match.Groups[1].Value) 'new' }
    Write-Fixture (Join-Path $releaseSource 'backend\requirements-runtime.txt') 'fixture'
    Write-Fixture (Join-Path $releaseSource 'version.txt') 'v2.0.0'
    Assert-Test (Test-NeveAppIntegrity $releaseSource).Ok 'complete release package passes integrity'
    $releaseZip=Join-Path $testRoot 'release.zip'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::CreateFromDirectory((Split-Path $releaseSource),$releaseZip)
    function Invoke-ReleaseDownload { param($Uri,$Destination);Copy-Item -LiteralPath $releaseZip -Destination $Destination }
    function Resolve-FrontendNodeLaunch { return @{NodeDir=$ROOT;NodeVersion='fixture';NpmVersion='fixture';NpmExecutable='fixture-npm'} }
    function Install-PortableNode22 { throw 'Unexpected real Node installation' }
    $script:FailurePhase=''
    $realRestore = (Get-Command Restore-ReleaseRollbackSnapshot).ScriptBlock
    function Restore-ReleaseRollbackSnapshot {
        param($SnapshotRoot,$DestinationRoot,$ExcludeDirs,$ExcludeFiles)
        if ($script:FailurePhase -eq 'rollback') { throw 'Injected rollback failure' }
        & $realRestore $SnapshotRoot $DestinationRoot $ExcludeDirs $ExcludeFiles
    }
    function Run {
        param($Executable,$Arguments,$Description,$Timeout)
        if ($Description -like 'npm run build*') {
            if ($script:FailurePhase -in @('build','rollback')) { return 1 }
            Write-Fixture (Join-Path $ROOT 'build\index.html') 'new frontend'
        }
        if ($Description -eq 'WebView2 Fixed e janela nativa') { Write-Fixture (Join-Path $ROOT '.desktop\installed.json') 'new desktop state' }
        if ($Description -eq 'validar inicializacao apos atualizacao' -and $script:FailurePhase -eq 'validation') { return 1 }
        return 0
    }
    foreach ($phase in @('success','build','validation','rollback')) {
        $ROOT=Join-Path $testRoot $phase
        [void][IO.Directory]::CreateDirectory($ROOT)
        Copy-Item -Path (Join-Path $releaseSource '*') -Destination $ROOT -Recurse
        Write-Fixture (Join-Path $ROOT '.env') 'user environment'
        Write-Fixture (Join-Path $ROOT 'version.txt') 'v1.0.0'
        Write-Fixture (Join-Path $ROOT 'backend\neveai\venv\Scripts\python.exe') 'python fixture'
        Write-Fixture (Join-Path $ROOT 'backend\neveai\venv\pyvenv.cfg') 'python fixture'
        Write-Fixture (Join-Path $ROOT 'backend\neveai\frontend\index.html') 'old frontend'
        Write-Fixture (Join-Path $ROOT 'backend\data\neve.db') 'user database'
        Write-Fixture (Join-Path $ROOT 'backend\data\cache\model.safetensors') 'user model'
        Write-Fixture (Join-Path $ROOT '.desktop\installed.json') 'old desktop state'
        Write-Fixture (Join-Path $ROOT 'node_modules\@officecli\officecli\vendor\officecli.exe') 'office fixture'
        Write-Fixture (Join-Path $ROOT 'logs\install-state.txt') 'done'
        $VERSION_FILE=Join-Path $ROOT 'version.txt';$currentVersion='v1.0.0';$latestTag='v2.0.0';$zipUrl='fixture';$script:FailurePhase=$phase
        $failed=$false
        try { $null=Update-NeveAI } catch { $failed=$true; $failureText=[string]$_ }
        Assert-Test ($failed -eq ($phase -ne 'success')) "update outcome: $phase $failureText"
        Assert-Test ([IO.File]::ReadAllText((Join-Path $ROOT '.env')) -eq 'user environment') "environment preserved: $phase"
        Assert-Test ([IO.File]::ReadAllText((Join-Path $ROOT 'backend\data\neve.db')) -eq 'user database') "database preserved: $phase"
        Assert-Test ([IO.File]::ReadAllText((Join-Path $ROOT 'backend\data\cache\model.safetensors')) -eq 'user model') "model cache preserved: $phase"
        $expectedVersion=if($phase -eq 'success'){'v2.0.0'}else{'v1.0.0'}
        $expectedFrontend=if($phase -eq 'success'){'new frontend'}else{'old frontend'}
        $expectedDesktop=if($phase -in @('success','rollback')){'new desktop state'}else{'old desktop state'}
        Assert-Test ([IO.File]::ReadAllText($VERSION_FILE) -eq $expectedVersion) "version transaction: $phase"
        Assert-Test ([IO.File]::ReadAllText((Join-Path $ROOT 'backend\neveai\frontend\index.html')) -eq $expectedFrontend) "frontend transaction: $phase"
        Assert-Test ([IO.File]::ReadAllText((Join-Path $ROOT '.desktop\installed.json')) -eq $expectedDesktop) "desktop transaction: $phase"
        if ($phase -eq 'rollback') {
            Assert-Test ([IO.File]::ReadAllText((Join-Path $ROOT 'logs\install-state.txt')) -eq 'failed') 'failed rollback blocks normal startup'
            $match=[regex]::Match($failureText,'Backup preservado em (.*?)\. Erro original')
            Assert-Test $match.Success 'failed rollback exposes backup location'
            $backup=[IO.Path]::GetFullPath($match.Groups[1].Value)
            $prefix=[IO.Path]::GetFullPath((Join-Path $env:TEMP 'neve_update_rollback_'))
            Assert-Test ($backup.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $backup)) "failed rollback keeps the recovery snapshot ($backup; prefix=$prefix)"
            $id=[regex]::Match((Split-Path $backup -Leaf),'^neve_update_rollback_([a-f0-9]{32})$').Groups[1].Value
            if (-not $id) { throw 'Unexpected recovery fixture path' }
            Remove-Item -LiteralPath $backup -Recurse -Force
            $envBackup=Join-Path $env:TEMP "neve_update_env_$id.bak"
            if (Test-Path -LiteralPath $envBackup) { Remove-Item -LiteralPath $envBackup -Force }
        }
    }
    $results | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $repo 'logs\installer-regressions.json') -Encoding UTF8
    Write-Output "$($results.Count) installer regression assertions passed"
} finally {
    Set-Location -LiteralPath $repo
    $resolved = [IO.Path]::GetFullPath($testRoot)
    if (-not $resolved.StartsWith((Join-Path $repo 'logs\installer-regressions-'),[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe test cleanup path' }
    if (Test-Path -LiteralPath $resolved) { Remove-Item -LiteralPath $resolved -Recurse -Force }
}
