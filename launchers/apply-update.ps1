param([Parameter(Mandatory=$true)][string]$Root,[Parameter(Mandatory=$true)][string]$Job,[switch]$ValidateOnly)
$ErrorActionPreference='Stop'
if($Job -notmatch '^[0-9a-f]{32}$'){throw 'Identificador de atualizacao invalido.'}
$ROOT=[IO.Path]::GetFullPath($Root).TrimEnd('\')
$jobRoot=Join-Path $ROOT "backend\data\updates\$Job"
$manifestPath=Join-Path $jobRoot 'manifest.json'
$manifest=ConvertFrom-Json ([IO.File]::ReadAllText($manifestPath,[Text.Encoding]::UTF8))
if([IO.Path]::GetFullPath([string]$manifest.root).TrimEnd('\') -ne $ROOT){throw 'A atualizacao pertence a outra instalacao.'}
if($manifest.status -notin @('ready','restarting')){throw 'O download da atualizacao nao esta pronto.'}
$targets=@($manifest.targets)
if(-not $targets.Count -or @($targets | Where-Object {$_ -notin @('neve','llama')}).Count){throw 'Destino de atualizacao invalido.'}
$files=@($manifest.packages | ForEach-Object {$_.file})
if(@($files | Select-Object -Unique).Count -ne $files.Count){throw 'Pacotes duplicados.'}
if(('neve' -in $targets) -ne ('neve.zip' -in $files) -or ('llama' -in $targets) -ne ('llama.zip' -in $files)){throw 'Os pacotes nao correspondem a selecao.'}
if('runtime.zip' -in $files -and 'llama' -notin $targets){throw 'Runtime sem atualizacao do llama.cpp.'}
if('neve' -in $targets -and $manifest.neve.tag -notmatch '^v?\d+(\.\d+)+([-+][\w.-]+)?$'){throw 'Versao do NeveAI invalida.'}
if('llama' -in $targets -and $manifest.llama.release.tag_name -notmatch '^b\d+$'){throw 'Versao do llama.cpp invalida.'}
foreach($package in @($manifest.packages)){
    if($package.file -notin @('neve.zip','llama.zip','runtime.zip') -or $package.sha256 -notmatch '^[0-9a-f]{64}$'){throw 'Pacote de atualizacao invalido.'}
    $path=Join-Path $jobRoot $package.file
    if(-not (Test-Path -LiteralPath $path) -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $package.sha256){throw 'O pacote de atualizacao foi alterado ou esta incompleto.'}
}
if(-not @($manifest.packages).Count){throw 'Nenhum pacote foi preparado.'}
# A different update may have been installed since these packages were downloaded.
if('neve' -in $targets -and (Test-Path -LiteralPath (Join-Path $ROOT 'version.txt'))){
    $installedVersion=$null;$preparedVersion=$null
    $installedTag=([IO.File]::ReadAllText((Join-Path $ROOT 'version.txt'))).Trim().TrimStart([char]0xFEFF) -replace '^v',''
    $preparedTag=([string]$manifest.neve.tag) -replace '^v',''
    if([version]::TryParse($installedTag,[ref]$installedVersion) -and [version]::TryParse($preparedTag,[ref]$preparedVersion) -and $preparedVersion -le $installedVersion){throw 'O pacote do NeveAI nao e mais recente que a instalacao atual.'}
}
if('llama' -in $targets -and (Test-Path -LiteralPath (Join-Path $ROOT 'llamacpp-server\version.txt'))){
    $installedTag=([IO.File]::ReadAllLines((Join-Path $ROOT 'llamacpp-server\version.txt')) | Select-Object -First 1).Trim().TrimStart([char]0xFEFF)
    if($installedTag -match '^b\d+$' -and [long]$installedTag.Substring(1) -ge [long]([string]$manifest.llama.release.tag_name).Substring(1)){throw 'O pacote do llama.cpp nao e mais recente que a instalacao atual.'}
}
if($ValidateOnly){exit 0}

. (Join-Path $PSScriptRoot 'update-core.ps1')
$LOG=Join-Path $ROOT 'logs\update.log'
New-Item -ItemType Directory -Force -Path (Split-Path $LOG) | Out-Null
$VERSION_FILE=Join-Path $ROOT 'version.txt'
$currentVersion=if(Test-Path -LiteralPath $VERSION_FILE){([IO.File]::ReadAllText($VERSION_FILE)).Trim()}else{''}
$latestTag=[string]$manifest.neve.tag
$zipUrl=[string]$manifest.neve.url
$UA='NeveAI-Updater'
$LLAMA_API_RELEASES='https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=30'
$updateNeve='neve' -in @($manifest.targets)
$updateLlama='llama' -in @($manifest.targets)
$UPDATE_CONTROL=@{CancelRequested=$false;Processes=[Collections.ArrayList]::new()}
function Write-UpdateState {
    $temporary="$manifestPath.tmp"
    [IO.File]::WriteAllText($temporary,($manifest | ConvertTo-Json -Depth 24),[Text.UTF8Encoding]::new($false))
    for($attempt=0;$attempt -lt 10;$attempt++){
        try{Move-Item -LiteralPath $temporary -Destination $manifestPath -Force -ErrorAction Stop;break}
        catch{if($attempt -eq 9){throw};Start-Sleep -Milliseconds 25}
    }
}
function L([string]$message,[string]$kind='info'){
    Add-Content -LiteralPath $LOG -Value "[$(Get-Date -Format 'HH:mm:ss')] $message" -Encoding UTF8
}
function P([int]$value,[string]$phase){
    $manifest.progress=[Math]::Max(0,[Math]::Min(100,$value))
    $manifest.phase=$phase
    Write-UpdateState
}
function Invoke-ReleaseDownload([string]$uri,[string]$destination){
    $package=@($manifest.packages | Where-Object {$_.url -eq $uri}) | Select-Object -First 1
    if(-not $package){throw "O pacote solicitado nao foi preparado: $uri"}
    Copy-Item -LiteralPath (Join-Path $jobRoot $package.file) -Destination $destination -Force -ErrorAction Stop
}
function Get-LatestLlamaRelease([string[]]$backends){return $manifest.llama.release}
function Get-LlamaHardwareTarget {
    return [pscustomobject]@{Vendor='installed';Name='';Label=[string]$manifest.llama.backend;Backends=@([string]$manifest.llama.backend);Reason='Preservar o backend instalado'}
}
try{
    $manifest.status='applying';$manifest.progress=0;Write-UpdateState
    if($updateNeve){[void](Update-NeveAI)}
    if($updateLlama){[void](Update-LlamaCpp)}
    $manifest.status='completed';P 100 'Atualizacao concluida'
    foreach($package in @($manifest.packages)){Remove-Item -LiteralPath (Join-Path $jobRoot $package.file) -Force -ErrorAction SilentlyContinue}
    exit 0
}catch{
    $manifest.status='failed'
    $manifest | Add-Member -NotePropertyName error -NotePropertyValue ([string]$_) -Force
    Write-UpdateState
    L "Falha: $_" 'err'
    exit 1
}
